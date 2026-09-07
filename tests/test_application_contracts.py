"""Coverage for application boundaries and extracted modules."""

from pathlib import Path

import logging

import pytest

import app as app_module
from app.config import Config
from app import create_app
from app.analysis import CmuPronunciationService, EslPhonicsEngine, REVIEWED_SYLLABLES
from app.config import settings
from app.repositories import WordBankRepository
from app.routes import api
from app.services.word_service import WordAnalysisService


@pytest.fixture
def isolated_service(tmp_path):
    return WordAnalysisService(
        db_path=str(tmp_path / "word-bank.sqlite3"),
        use_word_bank=True,
    )


def test_application_logging_writes_once_after_repeated_factory_calls(tmp_path, monkeypatch):
    log_path = tmp_path / "logs" / "app.log"
    monkeypatch.setattr(
        app_module,
        "settings",
        Config(log_file=str(log_path), log_level="DEBUG"),
    )

    create_app()
    create_app()
    logging.getLogger("app.test").debug("persistent logging smoke test")

    for handler in logging.getLogger("app").handlers:
        handler.flush()

    assert log_path.read_text(encoding="utf-8").count("persistent logging smoke test") == 1
    assert sum(
        getattr(handler, "syllabicator_handler", False)
        for handler in logging.getLogger("app").handlers
    ) == 4


def test_reviewed_beautiful_split_and_spelling_invariance(isolated_service):
    result = isolated_service.analyze("BEAUTIFUL")
    assert result["syllables"] == ["beau", "ti", "ful"]
    assert result["decoding"] == "béau-ti-ful"
    assert "".join(result["syllables"]) == "beautiful"


@pytest.mark.parametrize("word", ["beautiful", "english", "resignation", "aqueous", "adequately"])
def test_reviewed_splits_are_spelling_preserving(isolated_service, word):
    result = isolated_service.analyze(word)
    assert "".join(result["syllables"]) == word
    assert result["formatted"] == result["decoding"]


def test_generic_engine_handles_monovocalic_and_vowel_hiatus_words():
    engine = EslPhonicsEngine()
    assert engine.split_syllables("cat") == ["cat"]
    assert engine.split_syllables("poet") == ["po", "et"]
    assert engine.split_syllables("tackle") == ["tack", "le"]
    assert engine._reduce_affixes("unhappiness")[1:] == (["un"], ["ness"])


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("interpret", ("pret", ["inter"], [])),
        ("interpreted", ("pret", ["inter"], ["ed"])),
        ("interpreting", ("pret", ["inter"], ["ing"])),
        ("interpretation", ("pret", ["inter"], ["ation"])),
        ("misinterpret", ("pret", ["mis", "inter"], [])),
        ("misinterpreted", ("pret", ["mis", "inter"], ["ed"])),
        ("reinterpret", ("pret", ["re", "inter"], [])),
        ("reinterpreting", ("pret", ["re", "inter"], ["ing"])),
        ("involvement", ("volve", ["in"], ["ment"])),
    ],
)
def test_engine_reduces_common_prefix_and_suffix_families(word, expected):
    engine = EslPhonicsEngine()
    assert engine._reduce_affixes(word) == expected
    assert "".join(engine.split_syllables(word)) == word


@pytest.mark.parametrize(
    ("word", "expected"),
    [("knock", {"silent_vowels": [], "silent_consonants": [0]}),
     ("write", {"silent_vowels": [4], "silent_consonants": [0]}),
     ("lamb", {"silent_vowels": [], "silent_consonants": [3]}),
     ("aque", {"silent_vowels": [2, 3], "silent_consonants": []})],
)
def test_engine_silent_letter_guards(word, expected):
    assert EslPhonicsEngine().identify_silent_letters(word) == expected


def test_engine_boundary_repair_preserves_protected_units():
    engine = EslPhonicsEngine()
    assert engine._self_correct_boundaries(["fa", "shion"], "fashion") == ["fa", "shion"]
    assert engine._self_correct_boundaries(["eng", "l", "ish"], "english") == ["eng", "lish"]
    assert engine._self_correct_boundaries([], "") == []
    assert engine._self_correct_boundaries(["wrong"], "word") == ["word"]
    assert engine._self_correct_boundaries(["cat", "dog", "s"], "catdogs") == ["cat", "dogs"]


def test_engine_empty_and_repeated_boundary_guards():
    engine = EslPhonicsEngine()
    assert engine.split_syllables("") == []
    assert engine._generic_split("aia")
    assert engine._self_correct_boundaries(["a", "", "ia"], "aia") == ["a", "ia"]


def test_engine_reconciles_under_and_over_count_paths():
    engine = EslPhonicsEngine()
    assert engine._split_candidate("cat", 0, "cat") is None
    assert engine._split_candidate("tiona", 0, "tiona") is None
    assert engine._reconcile_count([], "cat", 1) == ["cat"]
    assert engine._reconcile_count(["cat"], "cat", 1) == ["cat"]
    assert engine._reconcile_count(["cat"], "cat", 2) == ["cat"]
    assert engine._reconcile_count(["cat", "aia"], "cataia", 3) == ["cat", "a", "ia"]
    assert engine._reconcile_count(["bu", "oy", "an", "cy"], "buoyancy", 3) == [
        "buoy", "an", "cy"
    ]
    assert engine._reconcile_count(["cat", "dog", "bird"], "catdogbird", 2) == [
        "cat", "dogbird"
    ]


def test_engine_inventory_returns_independent_lists(isolated_service):
    first = isolated_service.phonics_inventory()
    first["prefixes"].clear()
    second = isolated_service.phonics_inventory()
    assert second["prefixes"]
    assert isolated_service._engine.has_protected_split("fa", "shion") is False


@pytest.mark.parametrize("raw", [None, {}, 7, [], "  "])
def test_bulk_normalization_rejects_empty_or_invalid_values(raw):
    with pytest.raises((ValueError, TypeError)):
        WordAnalysisService._normalize_bulk_words(raw)


def test_bulk_normalization_supports_dicts_and_deduplicates():
    assert WordAnalysisService._normalize_bulk_words({"words": ["English", "english", "beautiful"]}) == [
        "english", "beautiful"
    ]
    assert WordAnalysisService._normalize_bulk_words(("one, two", "three")) == ["one", "two", "three"]
    assert WordAnalysisService._normalize_bulk_words({"text": "four five"}) == ["four", "five"]
    assert WordAnalysisService._normalize_bulk_words({"input": "six"}) == ["six"]
    assert WordAnalysisService._normalize_bulk_words({"word": "seven"}) == ["seven"]
    assert WordAnalysisService._normalize_bulk_words(["eight", None, "  ", "nine"]) == ["eight", "nine"]


@pytest.mark.parametrize(
    ("syllables", "index", "expected"),
    [([], 0, ""), (["one"], 3, "óne"), (["cat", "dog"], -1, "cát-dog"), (["sky"], 0, "ský")],
)
def test_stress_marker_handles_edges(syllables, index, expected):
    assert WordAnalysisService._add_stress_marker(syllables, index) == expected


@pytest.mark.parametrize(
    ("word", "expected"),
    [("cat", "A1"), ("word", "A2"), ("english", "B1"), ("beautiful", "B2"),
     ("syllabicator", "C1"), ("responsibilities", "C2")],
)
def test_cefr_boundaries(word, expected):
    assert WordAnalysisService._calculate_cefr(word) == expected


def test_repository_insert_update_lookup_and_foreign_keys(tmp_path):
    repository = WordBankRepository(tmp_path / "repository.sqlite3")
    record = {
        "word": "test", "normalized_word": "test", "syllables": ["test"],
        "stressed_syllable_index": 0, "decoding": "tést", "formatted": "tést",
        "cefr": "A1", "source": "user", "is_academic": False,
        "pos": "noun", "family": "testing", "notes": "first",
    }
    saved = repository.save(record)
    assert saved["word"] == "test"
    record["notes"] = "updated"
    assert repository.save(record)["notes"] == "updated"
    assert repository.lookup("missing") is None
    assert len(repository.list_words()) == 1
    with repository.connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_repository_reports_persistence_failure(monkeypatch, tmp_path):
    repository = WordBankRepository(tmp_path / "broken.sqlite3")
    record = {
        "word": "test", "normalized_word": "test", "syllables": ["test"],
        "stressed_syllable_index": 0, "decoding": "tést", "formatted": "tést",
        "cefr": "A1", "source": "user", "is_academic": False,
    }
    monkeypatch.setattr(repository, "lookup", lambda word: None)
    with pytest.raises(LookupError):
        repository.save(record)


def test_save_word_preserves_existing_metadata_and_updates_values(isolated_service):
    first = isolated_service.save_word("teacher", syllables=["teach", "er"], decoding="téach-er", pos="noun")
    second = isolated_service.save_word("teacher", notes="reviewed", source="import")
    assert second["id"] == first["id"]
    assert second["pos"] == "noun"
    assert second["notes"] == "reviewed"
    assert second["source"] == "import"


def test_service_validation_helpers_and_cmu_wrapper(isolated_service):
    with pytest.raises(ValueError):
        WordAnalysisService._normalize_word("")
    assert WordAnalysisService._clean_word_from_data(" English ") == "english"
    with pytest.raises(ValueError):
        WordAnalysisService._clean_word_from_data(None)
    assert WordAnalysisService._split_family_name(None) is None
    assert WordAnalysisService._split_family_name(" family ") == "family"
    assert WordAnalysisService._load_cmu_dict()
    assert isolated_service.analyze_many("one,two") == isolated_service.analyze_batch("one,two")
    assert isolated_service.bulk_analyze("three")[0]["word"] == "three"
    with pytest.raises(ValueError):
        isolated_service.save_word("bad", syllables="not-a-list")
    with pytest.raises(ValueError):
        isolated_service.save_word("bad", decoding=7)
    with pytest.raises(ValueError):
        isolated_service.save_word("bad", stress_index="0")


def test_word_bank_import_and_export_formats(isolated_service):
    csv_payload = "word,syllables,decoding\nalpha,al-pha,ál-pha\nbeta,be-ta,bé-ta\n"
    assert isolated_service.import_word_bank(csv_payload, "words.csv")["count"] == 2
    assert isolated_service.import_word_bank([{"word": "gamma", "syllables": "gam-ma"}], "words.json")["count"] == 1
    assert isolated_service.import_word_bank({"word": "jsonword"}, "words.json")["count"] == 1
    assert isolated_service.import_word_bank('[{"word": "jsontext"}]', "words.json")["count"] == 1
    assert isolated_service.import_word_bank([{"word": ""}, "plain"], "words.json")["count"] == 1
    assert isolated_service.import_word_bank(b"delta\nepsilon\n")["count"] == 2
    for format_name, suffix in [("csv", b"word,normalized_word"), ("xlsx", b"PK"), ("ods", b"PK")]:
        exported = isolated_service.export_word_bank(format_name)
        assert exported["filename"].endswith(format_name)
        assert exported["content"].startswith(suffix)
    with pytest.raises(ValueError):
        isolated_service.export_word_bank("txt")


def test_word_bank_decode_handles_scalar_and_csv_detection():
    from app.services.word_bank_io import WordBankIO

    assert WordBankIO._decode(12) == "12"
    assert WordBankIO._looks_like_csv("word,syllables\nalpha,al-pha") is True
    assert WordBankIO._looks_like_csv("alpha\nbeta") is False


def test_word_bank_optional_export_dependencies_fail_clearly(monkeypatch):
    import builtins

    from app.services.word_bank_io import WordBankIO

    original_import = builtins.__import__

    def reject_spreadsheets(name, *args, **kwargs):
        if name in {"openpyxl", "odf"}:
            raise ImportError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_spreadsheets)
    with pytest.raises(RuntimeError, match="XLSX"):
        WordBankIO._export_xlsx([], [])
    with pytest.raises(RuntimeError, match="ODS"):
        WordBankIO._export_ods([], [])


def test_api_supports_repeated_query_words_and_form_input():
    client = create_app().test_client()
    response = client.get("/api/analyze?words=english&words=beautiful")
    assert response.status_code == 200
    assert response.get_json()["count"] == 2
    response = client.post("/api/analyze", data={"word": "english"})
    assert response.status_code == 200
    assert response.get_json()["word"] == "english"
    response = client.post("/api/analyze", data="english\nbeautiful", content_type="text/plain")
    assert response.status_code == 200
    assert response.get_json()["count"] == 2
    assert client.get("/api/health").get_json() == {"status": "ok"}
    assert client.get("/api/analyze?text=english").status_code == 200
    assert client.post("/api/analyze", json={"word": "english"}).status_code == 200
    assert client.post("/api/analyze", json=["english", "beautiful"]).get_json()["count"] == 2
    assert client.post("/api/analyze", json=7).status_code == 400
    assert client.post("/api/analyze", json={"words": []}).status_code == 400
    assert client.post("/api/analyze/bulk", json={"word": "english"}).status_code == 200
    assert client.post("/api/bulk-analyze", json={"word": "english"}).status_code == 200
    assert client.post("/api/analyze", data={"input": "english"}).status_code == 200
    assert client.post("/api/analyze", data="   ", content_type="text/plain").status_code == 400
    assert client.get("/api/analyze").status_code == 400
    assert client.post("/api/analyze").status_code == 400


def test_v2_api_reports_explicit_cache_bypass():
    client = create_app().test_client()
    response = client.post(
        "/api/analyze?bypass=true",
        json={"word": ["resignation"]},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["cache_bypassed"] is True
    assert payload["results"][0]["decoding"] == "res-ig-ná-tion"


def test_api_translates_domain_and_unexpected_errors(monkeypatch):
    client = create_app().test_client()
    monkeypatch.setattr(api.service, "analyze", lambda word: (_ for _ in ()).throw(LookupError("missing")))
    assert client.get("/api/analyze/example").status_code == 404
    monkeypatch.setattr(api.service, "analyze", lambda word: (_ for _ in ()).throw(RuntimeError("secret")))
    response = client.get("/api/analyze/example")
    assert response.status_code == 500
    assert response.get_json() == {"error": "Unable to analyze the supplied word input."}


def test_web_routes_render_and_accept_lookup():
    client = create_app().test_client()
    assert client.get("/").status_code == 200
    assert client.post("/lookup", data={"word": "english"}).status_code == 200


def test_runtime_database_path_is_outside_source_package():
    database_path = Path(settings.database_path)
    assert database_path.name == "word_bank.sqlite3"
    assert database_path.parent != Path(__file__).parents[1] / "app"


def test_cmu_service_handles_known_and_unknown_words():
    assert CmuPronunciationService.vowel_count("english") == 2
    assert CmuPronunciationService.pronunciation("definitely-not-a-word") is None
    assert CmuPronunciationService.stress_index([], ["word"]) == 0
    assert CmuPronunciationService.stress_index(["AA0", "T", "EH1"], ["a"]) == 0


def test_cmu_download_path_is_safe(monkeypatch):
    calls = []
    monkeypatch.setattr(CmuPronunciationService, "_dictionary", None)
    monkeypatch.setattr("app.analysis.pronunciation.nltk.data.find", lambda path: (_ for _ in ()).throw(LookupError()))
    monkeypatch.setattr("app.analysis.pronunciation.nltk.download", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr("app.analysis.pronunciation.cmudict.dict", lambda: {"temporary": [["T", "EH1", "M"]]})
    assert CmuPronunciationService.pronunciation("temporary") == ["T", "EH1", "M"]
    assert calls == [("cmudict",)]


def _stress_test_words():
    source = Path(__file__).parents[1] / "docs" / "word-list-syllable-software-stress-test.txt"
    return [
        line.strip().lower()
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("---") and line.strip().lower() != "strengths"
    ]


def test_stress_test_corpus_matches_cmu_counts(isolated_service):
    for word in _stress_test_words():
        expected_count = CmuPronunciationService.vowel_count(word)
        result = isolated_service.analyze(word)
        assert "".join(result["syllables"]) == word
        if expected_count and word not in REVIEWED_SYLLABLES:
            assert len(result["syllables"]) == expected_count, word


def test_stress_test_unknown_words_use_reviewed_spelling_splits(isolated_service):
    unknown_words = [
        word for word in _stress_test_words()
        if not CmuPronunciationService.vowel_count(word)
    ]
    assert unknown_words
    assert set(unknown_words) <= set(REVIEWED_SYLLABLES)
    for word in unknown_words:
        result = isolated_service.analyze(word)
        assert result["syllables"] == REVIEWED_SYLLABLES[word]
        assert "".join(result["syllables"]) == word


@pytest.mark.parametrize("word", ["glimpsed", "scratched", "wrenched", "breathed", "judged", "fused"])
def test_monosyllabic_inflections_remain_one_spelling_chunk(isolated_service, word):
    result = isolated_service.analyze(word)
    assert result["syllables"] == [word]
    assert result["stressed_syllable_index"] == 0


def test_acquaint_uses_primary_cmu_stress_ordinal(isolated_service):
    result = isolated_service.analyze("acquaint")
    assert result["syllables"] == ["ac", "quaint"]
    assert result["stressed_syllable_index"] == 1


@pytest.mark.parametrize(
    ("word", "expected", "decoding"),
    [
        (
            "uncharacteristically", ["un", "char", "ac", "ter", "is", "tic", "al", "ly"],
            "un-char-ac-ter-ís-tic-al-ly",
        ),
        (
            "otolaryngologist", ["o", "to", "lar", "yng", "ol", "o", "gist"],
            "ó-to-lar-yng-ol-o-gist",
        ),
        (
            "electroencephalography", ["e", "lec", "tro", "en", "ceph", "a", "lo", "graph", "y"],
            "é-lec-tro-en-ceph-a-lo-graph-y",
        ),
        (
            "honorificabilitudinitatibus",
            ["hon", "or", "i", "fi", "ca", "bil", "i", "tu", "din", "i", "ta", "ti", "bus"],
            "hon-or-i-fi-ca-bil-i-tu-din-i-tá-ti-bus",
        ),
        (
            "antidisestablishmentarianism",
            ["an", "ti", "dis", "es", "tab", "lish", "ment", "ar", "i", "an", "ism"],
            "an-ti-dis-es-tab-lish-ment-ár-i-an-ism",
        ),
        ("pharaoh", ["phar", "aoh"], "phár-aoh"),
        ("khaki", ["khak", "i"], "khák-i"),
        ("mnemonic", ["mne", "mon", "ic"], "mne-món-ic"),
        ("psychology", ["psy", "chol", "o", "gy"], "psy-chól-o-gy"),
    ],
)
def test_priority_reviewed_splits_match_the_teaching_contract(isolated_service, word, expected, decoding):
    result = isolated_service.analyze(word)
    assert result["syllables"] == expected
    assert result["decoding"] == decoding
    assert "".join(expected) == word


@pytest.mark.parametrize(
    ("word", "expected", "decoding"),
    [
        ("aggression", ["ag", "gres", "sion"], "ag-grés-sion"),
        ("accommodate", ["ac", "com", "mod", "ate"], "ac-cóm-mod-ate"),
        ("orchard", ["or", "chard"], "ór-chard"),
        ("dolphin", ["dol", "phin"], "dól-phin"),
        ("pilgrimage", ["pil", "grim", "age"], "píl-grim-age"),
        ("monster", ["mon", "ster"], "món-ster"),
        ("bankruptcy", ["bank", "rup", "tcy"], "bánk-rup-tcy"),
        ("athlete", ["ath", "lete"], "áth-lete"),
        ("abstract", ["ab", "stract"], "ab-stráct"),
        ("interstate", ["in", "ter", "state"], "in-ter-státe"),
        ("transatlantic", ["trans", "at", "lan", "tic"], "trans-at-lán-tic"),
        ("misunderstand", ["mis", "un", "der", "stand"], "mis-un-der-stánd"),
        ("disagree", ["dis", "a", "gree"], "dis-a-grée"),
        ("nuthatch", ["nut", "hatch"], "nút-hatch"),
        ("bookshelf", ["book", "shelf"], "bóok-shelf"),
        ("unbelievable", ["un", "be", "liev", "a", "ble"], "un-be-líev-a-ble"),
        ("definitively", ["de", "fin", "i", "tive", "ly"], "de-fín-i-tive-ly"),
        ("hopping", ["hop", "ping"], "hóp-ping"),
        ("tableware", ["ta", "ble", "ware"], "tá-ble-ware"),
        ("acquaint", ["ac", "quaint"], "ac-quáint"),
        ("choir", ["choir"], "chóir"),
        ("penguin", ["pen", "guin"], "pén-guin"),
        ("zoology", ["zo", "ol", "o", "gy"], "zo-ól-o-gy"),
    ],
)
def test_listed_common_cause_corrections(isolated_service, word, expected, decoding):
    result = isolated_service.analyze(word)
    assert result["syllables"] == expected
    assert result["decoding"] == decoding


@pytest.mark.parametrize(
    ("word", "expected", "decoding"),
    [
        ("grocery", ["gro", "cer", "y"], "gró-cer-y"),
        ("atmosphere", ["at", "mos", "phere"], "át-mos-phere"),
        ("hemisphere", ["hem", "i", "sphere"], "hém-i-sphere"),
        ("landscape", ["land", "scape"], "lánd-scape"),
        ("blindfold", ["blind", "fold"], "blínd-fold"),
        ("crossroad", ["cross", "road"], "cróss-road"),
        ("hardware", ["hard", "ware"], "hárd-ware"),
        ("software", ["soft", "ware"], "sóft-ware"),
        ("solemn", ["sol", "emn"], "sól-emn"),
        ("damnation", ["dam", "na", "tion"], "dam-ná-tion"),
        ("column", ["col", "umn"], "cól-umn"),
        ("galaxy", ["gal", "ax", "y"], "gál-ax-y"),
        ("exit", ["ex", "it"], "éx-it"),
        ("examine", ["ex", "am", "ine"], "ex-ám-ine"),
        ("luxury", ["lux", "ur", "y"], "lúx-ur-y"),
        ("wizard", ["wiz", "ard"], "wíz-ard"),
        ("maximum", ["max", "i", "mum"], "máx-i-mum"),
        ("horizon", ["hor", "i", "zon"], "hor-í-zon"),
        ("citizen", ["cit", "i", "zen"], "cít-i-zen"),
        ("casual", ["cas", "u", "al"], "cás-u-al"),
        ("dual", ["du", "al"], "dú-al"),
        ("fuel", ["fu", "el"], "fú-el"),
        ("cruel", ["cru", "el"], "crú-el"),
        ("grueling", ["gru", "el", "ing"], "grú-el-ing"),
        ("fluid", ["flu", "id"], "flú-id"),
    ],
)
def test_new_compound_and_hiatus_corrections(isolated_service, word, expected, decoding):
    result = isolated_service.analyze(word)
    assert result["syllables"] == expected
    assert result["decoding"] == decoding
    assert "".join(expected) == word


def test_ism_suffix_is_inviolable_and_reductions_restart_from_the_left():
    engine = EslPhonicsEngine()
    assert engine._self_correct_boundaries(["root", "is", "m"], "rootism") == ["root", "ism"]
    assert engine._reduce_affixes("unhappiness") == ("happi", ["un"], ["ness"])


def test_priority_irregulars_are_seeded_into_the_reviewed_word_bank(tmp_path):
    service = WordAnalysisService(
        db_path=str(tmp_path / "seeded.sqlite3"),
        use_word_bank=True,
    )
    saved = service.lookup_word("pharaoh")
    assert saved is not None
    assert saved["syllables"] == ["phar", "aoh"]
    assert service.analyze("pharaoh")["source"] == "rule-based"
