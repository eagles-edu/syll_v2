"""Provider, compound, disagreement, and idempotency contracts."""

import json
import logging
from urllib.error import URLError

from app.analysis.compound import CompoundResolver
from app.analysis.phonics_engine import EslPhonicsEngine
from app.analysis.tracing import AnalysisTrace
from app.logging_config import LogicDisagreementHandler, _resolve_level, setup_logging
from app.providers import MerriamWebsterProvider, MerriamWebsterResult
from app.providers.merriam_webster import _parse_headword, _pronunciation, _stress_index
from app.services.word_service import WordAnalysisService


def _mw_payload(headword="voluminous", pronunciation="və-ˈlü-mə-nəs"):
    return [{
        "meta": {"id": headword},
        "hwi": {"hw": "vo*lu*mi*nous", "prs": [{"mw": pronunciation}]},
        "fl": "adjective",
    }]


def test_mw_parser_selects_matching_entry_and_extracts_stress():
    provider = MerriamWebsterProvider(
        api_key="test-key",
        transport=lambda word, timeout: [
            {"meta": {"id": "volume"}, "hwi": {"hw": "vol*ume"}},
            *_mw_payload(),
        ],
    )

    result = provider.lookup("voluminous")

    assert result == MerriamWebsterResult(
        word="voluminous",
        syllables=("vo", "lu", "mi", "nous"),
        pronunciation="və-ˈlü-mə-nəs",
        stress_index=1,
    )


def test_mw_parser_rejects_unsafe_payloads_and_caches_failure():
    calls = []
    provider = MerriamWebsterProvider(
        api_key="test-key",
        transport=lambda word, timeout: calls.append(word) or {"not": "a list"},
    )

    assert provider.lookup("unknown") is None
    assert provider.lookup("unknown") is None
    assert calls == ["unknown"]


def test_mw_provider_transport_failure_is_cached_and_fail_open():
    calls = []

    def failing_transport(word, timeout):
        calls.append((word, timeout))
        raise URLError("offline")

    provider = MerriamWebsterProvider(api_key="test-key", transport=failing_transport)

    assert provider.lookup("voluminous") is None
    assert provider.lookup("voluminous") is None
    assert len(calls) == 1


def test_mw_parser_rejects_invalid_entries_and_handles_missing_pronunciation():
    invalid = [
        None,
        {},
        {"meta": {}, "hwi": {}},
        {"meta": {"id": "other"}, "hwi": {"hw": "vo*lu*mi*nous"}},
        {"meta": {"id": "voluminous"}, "hwi": {"hw": 3}},
        {"meta": {"id": "voluminous"}, "hwi": {"hw": "vo*lu*mi*?"}},
        {"meta": {"id": "voluminous"}, "hwi": {"hw": "wrong"}},
    ]
    payload = invalid + [{"meta": {"id": "voluminous"}, "hwi": {"hw": "vo*lu*mi*nous"}}]
    provider = MerriamWebsterProvider(api_key="test-key", transport=lambda word, timeout: payload)

    result = provider.lookup("voluminous")

    assert result is not None
    assert result.syllables == ("vo", "lu", "mi", "nous")
    assert result.pronunciation is None
    assert result.stress_index is None


def test_mw_parser_rejection_helpers_cover_bad_shapes_and_stressless_pronunciation():
    assert MerriamWebsterProvider._parse_payload("word", [None, {}, {"meta": {}, "hwi": {}}])[0] is None
    assert _parse_headword("word", "wo*rd!") is None
    assert _parse_headword("word", "other") is None
    assert _pronunciation(None) is None
    assert _pronunciation([{}, {"mw": ""}]) is None
    assert _stress_index("foo-bar") is None


def test_mw_entry_rejects_non_string_and_mismatched_headword_data():
    payload = [
        {"meta": {"id": "word"}, "hwi": {"hw": 3}},
        {"meta": {"id": "word"}, "hwi": {"hw": "wrong"}},
    ]
    assert MerriamWebsterProvider._parse_payload("word", payload)[0] is None


def test_mw_request_json_enforces_response_size_and_decodes_json(monkeypatch):
    class Response:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self, _size):
            return self.body

    provider = MerriamWebsterProvider(api_key="test-key")
    monkeypatch.setattr(
        "app.providers.merriam_webster.urlopen",
        lambda request, timeout: Response(b"[]"),
    )
    assert provider._request_json("word", 1) == []
    monkeypatch.setattr(
        "app.providers.merriam_webster.urlopen",
        lambda request, timeout: Response(b"x" * 1_048_577),
    )
    try:
        provider._request_json("word", 1)
    except ValueError as error:
        assert str(error) == "response_too_large"
    else:
        raise AssertionError("oversized provider responses must be rejected")


def test_mw_disabled_is_fail_open():
    provider = MerriamWebsterProvider()

    assert provider.enabled is False
    assert provider.lookup("voluminous") is None


def test_compound_resolver_requires_lexicon_and_cmu_evidence(tmp_path):
    lexicon = tmp_path / "words"
    lexicon.write_text("sign\npost\nair\nport\nEric\n", encoding="utf-8")
    pronunciations = {
        "sign": ["S", "AY1", "N"],
        "post": ["P", "OW1", "S", "T"],
        "airport": ["EH1", "R", "P", "AO2", "R", "T"],
        "air": ["EH1", "R"],
        "port": ["P", "AO1", "R", "T"],
        "eric": ["EH1", "R", "IH0", "K"],
    }
    def pronunciation(word):
        return pronunciations.get(word)

    resolver = CompoundResolver(pronunciation, lexicon_path=lexicon)

    assert resolver.resolve("signpost") == ["sign", "post"]
    assert resolver.resolve("airport") == ["air", "port"]
    assert resolver.resolve("eric") is None


def test_compound_resolver_falls_back_when_lexicon_file_is_missing(tmp_path):
    def pronunciation(word):
        return {"sign": ["S", "AY1", "N"], "post": ["P", "OW1", "S", "T"]}.get(word)

    resolver = CompoundResolver(
        pronunciation,
        lexicon_path=tmp_path / "missing-words",
    )

    assert resolver.resolve("signpost") == ["sign", "post"]


def test_engine_reconciliation_guard_stops_non_progressing_splits():
    engine = EslPhonicsEngine()

    def no_progress(_chunk, _offset, _word):
        return 0

    engine._split_candidate = no_progress

    result = engine._reconcile_count(["word"], "word", 100)

    assert "".join(result) == "word"


def test_engine_explicit_hyphen_and_compound_boundary_exception_paths():
    engine = EslPhonicsEngine()

    assert engine.split_syllables("over-estimate")
    assert engine.has_protected_split("nut", "hatch") is False


def test_mw_authority_and_word_bank_idempotency(tmp_path):
    provider_calls = []

    def lookup(word):
        provider_calls.append(word)
        return MerriamWebsterResult(
            word=word,
            syllables=("vo", "lu", "mi", "nous"),
            pronunciation="və-ˈlü-mə-nəs",
            stress_index=1,
        )

    class StubProvider:
        enabled = True

        def lookup(self, word):
            return lookup(word)

    service = WordAnalysisService(
        db_path=str(tmp_path / "words.sqlite3"),
        use_word_bank=True,
        bypass_cache=False,
        mw_provider=StubProvider(),
    )

    first = service.analyze("voluminous")
    second = service.analyze("voluminous")

    assert first == second
    assert first["source"] == "merriam-webster"
    assert first["from_word_bank"] is True
    assert provider_calls == ["voluminous"]
    assert len(service.list_saved_words()) == len({item["normalized_word"] for item in service.list_saved_words()})


def test_disagreement_handler_writes_one_structured_event(tmp_path):
    path = tmp_path / "logic-disagreements.jsonl"
    handler = LogicDisagreementHandler(path, maxBytes=100000, backupCount=1, encoding="utf-8")
    logger = logging.getLogger("test.disagreement.handler")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info(
            "logic disagreement",
            extra={"logic_disagreement": {"word": "signpost", "decision": "merriam_webster_authoritative"}},
        )
    finally:
        logger.removeHandler(handler)
        handler.close()

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["event"]["word"] == "signpost"
    assert record["event"]["decision"] == "merriam_webster_authoritative"


def test_setup_logging_configures_trace_and_disagreement_outputs(tmp_path):
    log_file = tmp_path / "app.log"
    trace_file = tmp_path / "analysis-trace-log.md"
    disagreement_file = tmp_path / "logic-disagreements.jsonl"
    setup_logging(str(log_file), "DEBUG", str(trace_file), str(disagreement_file))
    logger = logging.getLogger("app.test.setup")
    try:
        logger.info(
            "logic disagreement",
            extra={"logic_disagreement": {"word": "signpost", "decision": "mw"}},
        )
        for handler in logging.getLogger("app").handlers:
            handler.flush()
    finally:
        for handler in logging.getLogger("app").handlers[:]:
            if getattr(handler, "syllabicator_handler", False):
                logging.getLogger("app").removeHandler(handler)
                handler.close()

    assert json.loads(disagreement_file.read_text(encoding="utf-8"))["event"]["word"] == "signpost"


def test_logging_filters_and_trace_error_resolution(tmp_path):
    handler = LogicDisagreementHandler(
        tmp_path / "ignored.jsonl",
        maxBytes=100000,
        backupCount=1,
    )
    try:
        handler.emit(logging.makeLogRecord({"msg": "ignored", "args": ()}))
    finally:
        handler.close()
    trace = AnalysisTrace("word")
    trace.emit("TEST", "error_node", "input", {"status": "error"})
    assert trace.events[0].resolution == "error"
    try:
        _resolve_level("not-a-level")
    except ValueError as error:
        assert "Unsupported log level" in str(error)
    else:
        raise AssertionError("invalid levels must be rejected")
