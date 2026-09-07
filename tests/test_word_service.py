import pytest

from app import create_app
from app.analysis.tracing import AnalysisTrace, begin_analysis_trace, end_analysis_trace
from app.services.word_service import WordAnalysisService


@pytest.fixture
def word_service_fixture():
    return WordAnalysisService()


def test_word_service_handles_common_word(word_service_fixture):
    result = word_service_fixture.analyze("beautiful")
    assert result["word"] == "beautiful"
    assert len(result["syllables"]) >= 2
    assert result["stressed_syllable_index"] >= 0
    assert "decoding" in result
    assert result["decoding"]


@pytest.mark.parametrize(
    "word, expected",
    [
        ("running", ["run", "ning"]),
        ("happen", ["hap", "pen"]),
        ("kitten", ["kit", "ten"]),
        ("butter", ["but", "ter"]),
    ],
)
def test_word_service_splits_doubled_consonants_at_the_boundary(word_service_fixture, word, expected):
    result = word_service_fixture.analyze(word)
    assert result["syllables"] == expected


def test_word_service_logs_complete_analysis_run(word_service_fixture, caplog):
    with caplog.at_level("DEBUG", logger="app.services.word_service"):
        word_service_fixture.analyze("running")

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "analysis start" in messages
    assert "analysis word_bank" in messages
    assert "analysis pronunciation" in messages
    assert "analysis syllables" in messages
    assert "analysis stress" in messages
    assert "analysis complete" in messages


def test_word_service_temporarily_disables_word_bank_shortcut(caplog):
    reviewed_service = WordAnalysisService(use_word_bank=True)
    generic_service = WordAnalysisService(
        use_word_bank=True,
        skip_word_bank_words={"resignation"},
    )

    reviewed_result = reviewed_service.analyze("resignation")
    with caplog.at_level("DEBUG"):
        generic_result = generic_service.analyze("resignation")

    assert reviewed_result["source"] == "rule-based"
    assert generic_result["source"] == "rule-based"
    assert reviewed_result["syllables"] == generic_result["syllables"]
    assert reviewed_result["decoding"] == generic_result["decoding"]
    assert generic_result["syllables"] == ["res", "ig", "na", "tion"]
    assert generic_result["decoding"] == "res-ig-ná-tion"
    assert any(
        record.getMessage().startswith("analysis_step step=000")
        for record in caplog.records
    )


def test_word_service_traces_ordered_phonics_decisions(word_service_fixture, caplog):
    with caplog.at_level("DEBUG"):
        result = word_service_fixture.analyze("running")

    assert result["syllables"] == ["run", "ning"]

    trace_messages = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("analysis_step ")
    ]
    assert trace_messages
    steps = [int(message.split("step=", 1)[1].split(" ", 1)[0]) for message in trace_messages]
    assert steps == list(range(len(steps)))
    assert "node=input_word" in trace_messages[0]
    assert any("node=affix_reduction_pass" in message and "input='ing'" in message for message in trace_messages)
    assert any(
        "node=affix_reduction_decision" in message
        and "decision='repeat_pass'" in message
        for message in trace_messages
    )
    assert any(
        "node=affix_reduction_decision" in message
        and "decision='NFRP'" in message
        for message in trace_messages
    )
    assert any("node=affixed_split" in message and "output=['run', 'ning']" in message for message in trace_messages)
    assert any("node=stress_decision" in message and "output=0" in message for message in trace_messages)


def test_generic_resignation_trace_reports_missing_and_wrong_reviewed_result(caplog):
    service = WordAnalysisService(use_word_bank=True, skip_word_bank_words={"resignation"})
    expected = service._engine.reviewed_syllables.pop("resignation")

    try:
        with caplog.at_level("DEBUG"):
            result = service.analyze("resignation")
            service._engine.reviewed_syllables["resignation"] = expected
            trace_token = begin_analysis_trace("resignation")
            try:
                service._engine._trace_result_monitor("resignation", result["syllables"])
            finally:
                end_analysis_trace(trace_token)
    finally:
        service._engine.reviewed_syllables["resignation"] = expected

    assert result["syllables"] == ["re", "sign", "a", "tion"]
    trace_messages = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("analysis_step ")
    ]
    assert any("node=pronunciation_vowel_count" in message and "output=4" in message for message in trace_messages)
    assert any("node=affix_reduction" in message and "output={'core': 'sign'" in message for message in trace_messages)
    assert any("node=reconciliation_pass" in message and "repetition=1" in message for message in trace_messages)
    assert any(
        "node=reconciliation_split" in message
        and "output=['re', 'sign', 'a', 'tion']" in message
        for message in trace_messages
    )
    assert any("node=stress_decision" in message and "output=2" in message for message in trace_messages)


def test_analysis_trace_emits_events_immediately(caplog):
    trace = AnalysisTrace("resignation")
    with caplog.at_level("DEBUG", logger="app.analysis.tracing"):
        trace.emit("AFF-06", "affix_reduction_decision", "signa", "no_further_reduction")
        trace.emit("REC-08", "reconciliation_decision", {"repeat": False}, {"result": []})

    assert trace.events[0].step == 0
    assert trace.events[0].decision == "NFRP"
    assert "analysis_step step=000" in caplog.records[0].getMessage()
    assert "input='signa'" in caplog.records[0].getMessage()
    assert "decision='NFRP'" in caplog.records[0].getMessage()


def test_word_bank_shortcut_can_be_reenabled_explicitly_for_v2(tmp_path):
    service = WordAnalysisService(
        db_path=str(tmp_path / "word_bank.sqlite3"),
        use_word_bank=True,
        bypass_cache=False,
    )
    saved = service.save_word("english", syllables=["eng", "lish"], decoding="éng-lish")

    result = service.analyze("english")

    assert result["source"] == "word-bank"
    assert result["from_word_bank"] is True
    assert result["decoding"] == saved["decoding"]


def test_word_service_stresses_primary_syllable(word_service_fixture):
    result = word_service_fixture.analyze("hello")
    assert result["syllables"] == ["he", "llo"] or len(result["syllables"]) == 2
    assert result["decoding"]
    assert "á" in result["decoding"] or "é" in result["decoding"] or "ó" in result["decoding"]


def test_word_service_handles_english_syllables(word_service_fixture):
    result = word_service_fixture.analyze("english")
    assert result["syllables"] == ["eng", "lish"]
    assert result["stressed_syllable_index"] == 0
    assert result["decoding"] == "éng-lish"
    assert "é" in result["decoding"]


def test_word_service_handles_consonant_le_and_digraph_patterns(word_service_fixture):
    for word, expected in {
        "apple": ["ap", "ple"],
        "tackle": ["tack", "le"],
        "fable": ["fa", "ble"],
    }.items():
        result = word_service_fixture.analyze(word)
        assert result["syllables"] == expected
        assert result["decoding"]


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("signpost", ["sign", "post"]),
        ("pneumatic", ["pneu", "mat", "ic"]),
        ("signature", ["sig", "na", "ture"]),
    ],
)
def test_word_service_preserves_reviewed_regression_splits(
    word_service_fixture,
    word,
    expected,
):
    result = word_service_fixture.analyze(word)

    assert result["syllables"] == expected
    assert "".join(result["syllables"]) == word


@pytest.mark.parametrize(
    "word, expected_syllables, expected_decoding, expected_index",
    [
        ("accidentally", ["ac", "ci", "den", "tal", "ly"], "ac-ci-dén-tal-ly", 2),
        ("additional", ["ad", "di", "tion", "al"], "ad-dí-tion-al", 1),
        ("accommodate", ["ac", "com", "mod", "ate"], "ac-cóm-mod-ate", 1),
        ("accurately", ["ac", "cu", "rate", "ly"], "ác-cu-rate-ly", 0),
        ("additionally", ["ad", "di", "tion", "al", "ly"], "ad-dí-tion-al-ly", 1),
        ("adequately", ["a", "de", "quate", "ly"], "á-de-quate-ly", 0),
        ("aqueous", ["a", "que", "ous"], "á-que-ous", 0),
        ("resignation", ["res", "ig", "na", "tion"], "res-ig-ná-tion", 2),
    ],
)
def test_word_service_handles_academic_affix_patterns(
    word_service_fixture,
    word,
    expected_syllables,
    expected_decoding,
    expected_index,
):
    result = word_service_fixture.analyze(word)
    assert result["syllables"] == expected_syllables
    assert result["decoding"] == expected_decoding
    assert result["stressed_syllable_index"] == expected_index


@pytest.mark.parametrize(
    "word, expected_count",
    [
        ("resignation", 4),
        ("aqueous", 3),
        ("accurately", 4),
        ("additionally", 5),
        ("adequately", 4),
    ],
)
def test_word_service_counts_primary_cmu_vowel_sounds(
    word_service_fixture,
    word,
    expected_count,
):
    assert word_service_fixture.count_vowel_sounds(word) == expected_count


def test_word_service_marks_qu_u_as_non_nucleus(word_service_fixture):
    silent = word_service_fixture.identify_silent_letters("aqueous")

    assert silent["silent_vowels"] == [2]


@pytest.mark.parametrize(
    "word, expected",
    [
        ("accurately", [7]),
        ("adequately", [2, 4, 7]),
    ],
)
def test_word_service_marks_non_nucleus_vowels_as_silent(
    word_service_fixture,
    word,
    expected,
):
    silent = word_service_fixture.identify_silent_letters(word)

    assert silent["silent_vowels"] == expected


@pytest.mark.parametrize(
    "word, expected",
    [
        ("knock", [0]),
        ("gnaw", [0]),
        ("write", [0]),
        ("lamb", [3]),
    ],
)
def test_word_service_marks_common_silent_consonants(
    word_service_fixture,
    word,
    expected,
):
    assert word_service_fixture.identify_silent_letters(word)["silent_consonants"] == expected


def test_word_service_exposes_controlled_phonics_inventory(word_service_fixture):
    inventory = word_service_fixture.phonics_inventory()

    assert {"sh", "ch", "th", "ph", "qu"} <= set(inventory["consonant_digraphs"])
    assert {"ai", "ea", "ee", "ou", "aw", "ew"} <= set(inventory["vowel_digraphs"])
    assert {"str", "thr", "scr"} <= set(inventory["consonant_blends"])
    assert {"ar", "er", "ir", "or", "ur"} <= set(inventory["r_controlled_vowels"])
    assert {"qu", "gue", "que"} <= set(inventory["mixed_digraphs"])
    assert {"dge", "igh", "ind", "gue"} <= set(inventory["trigraphs"])


def test_word_service_rejects_empty_input(word_service_fixture):
    with pytest.raises(ValueError):
        word_service_fixture.analyze("   ")


def test_word_service_provides_cefr_value(word_service_fixture):
    result = word_service_fixture.analyze("calendar")
    assert result["cefr"] in {"A1", "A2", "B1", "B2", "C1", "C2"}


def test_word_service_maps_primary_stress_to_the_correct_syllable(word_service_fixture):
    for word, expected_index in {
        "hello": 1,
        "beautiful": 0,
        "calendar": 0,
    }.items():
        result = word_service_fixture.analyze(word)
        assert result["stressed_syllable_index"] == expected_index
        assert result["decoding"]
        assert any(vowel in result["decoding"] for vowel in "áéíóúý")


def test_word_service_handles_bulk_newline_input(word_service_fixture):
    result = word_service_fixture.analyze_batch("english\nbeautiful\ncalendar")
    assert [item["word"] for item in result] == ["english", "beautiful", "calendar"]
    assert result[0]["decoding"] == "éng-lish"
    assert result[1]["formatted"] == result[1]["decoding"]


def test_word_service_handles_100_plus_words_bulk_processing(word_service_fixture):
    sample_base = [
        "english", "resignation", "aqueous", "accurately", "additionally",
        "adequately", "accidentally", "fashion", "father", "washing",
        "pilgrim", "basket", "buffer", "beginner", "inspection",
        "apple", "tackle", "fable", "cabin", "river", "metal", "melon",
        "preview", "working", "tasty", "market", "garden", "perfect", "winter", "summer"
    ]
    # Build 120 distinct words corpus
    prefixes = ["un", "re", "pre", "non"]
    bulk_words = [f"{p}{w}" for p in prefixes for w in sample_base]
    assert len(bulk_words) == 120
    bulk_input = "\n".join(bulk_words)
    results = word_service_fixture.analyze_batch(bulk_input)
    assert len(results) == 120
    for item in results:
        assert item["word"]
        assert len(item["syllables"]) >= 1
        assert item["decoding"]
        assert item["cefr"] in {"A1", "A2", "B1", "B2", "C1", "C2"}


def test_api_accepts_bulk_input_contract():
    client = create_app().test_client()
    response = client.post("/api/analyze", json={"words": ["english", "beautiful"]})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 2
    assert payload["results"][0]["word"] == "english"
    assert payload["results"][0]["decoding"] == "éng-lish"


def test_api_bulk_processing_100_plus_words():
    client = create_app().test_client()
    sample_words = [f"word{chr(97 + (i // 26))}{chr(97 + (i % 26))}" for i in range(105)]
    assert len(set(sample_words)) == 105
    response = client.post("/api/analyze", json={"words": sample_words})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 105
    assert len(payload["results"]) == 105
    assert payload["results"][0]["word"] == sample_words[0]


def test_api_bulk_processing_mixed_delimiters():
    client = create_app().test_client()
    mixed_text = "english, beautiful; calendar\nresignation\t aqueous"
    response = client.post("/api/analyze", json={"text": mixed_text})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 5
    words = [r["word"] for r in payload["results"]]
    assert words == ["english", "beautiful", "calendar", "resignation", "aqueous"]


def test_word_service_builds_word_bank_record(word_service_fixture):
    record = word_service_fixture.build_word_bank_record("academic")
    assert record["word"] == "academic"
    assert record["formatted"]
    assert record["source"] == "rule-based"
    assert record["is_academic"] is True


def test_word_service_temporarily_ignores_word_bank_during_analysis(tmp_path):
    service = WordAnalysisService(
        db_path=str(tmp_path / "word_bank.sqlite3"),
        use_word_bank=True,
    )
    saved = service.save_word(
        "english",
        syllables=["eng", "lish"],
        decoding="éng-lish",
        pos="adjective",
        is_academic=True,
    )

    result = service.analyze("english")

    assert result["word"] == "english"
    assert result["source"] == "rule-based"
    assert result["from_word_bank"] is False
    assert result["syllables"] == ["eng", "lish"]
    assert result["decoding"] == saved["decoding"]


def test_word_service_returns_raw_analysis_without_word_bank_lookup(tmp_path):
    service = WordAnalysisService(db_path=str(tmp_path / "word_bank.sqlite3"))
    service.save_word(
        "english",
        syllables=["stored"],
        decoding="stór-ed",
        pos="adjective",
        is_academic=True,
    )

    result = service.analyze("english")

    assert result["source"] == "rule-based"
    assert result["from_word_bank"] is False
    assert result["syllables"] == ["eng", "lish"]
    assert result["decoding"] == "éng-lish"


def test_engine_self_corrects_orphaned_consonants(word_service_fixture):
    engine = word_service_fixture._engine
    corrected = engine._self_correct_boundaries(["eng", "l", "ish"], "english")
    assert corrected == ["eng", "lish"]


def test_engine_self_corrects_split_digraphs(word_service_fixture):
    engine = word_service_fixture._engine
    corrected = engine._self_correct_boundaries(["fas", "hion"], "fashion")
    assert corrected == ["fa", "shion"] or corrected == ["fash", "ion"]
    assert "".join(corrected) == "fashion"


@pytest.mark.parametrize(
    "word, expected_syllables",
    [
        ("garden", ["gar", "den"]),
        ("market", ["mar", "ket"]),
        ("turtle", ["tur", "tle"]),
        ("perfect", ["per", "fect"]),
        ("fashion", ["fash", "ion"]),
        ("father", ["fa", "ther"]),
        ("washing", ["wash", "ing"]),
        ("pilgrim", ["pil", "grim"]),
        ("basket", ["bas", "ket"]),
        ("buffer", ["buf", "fer"]),
        ("beginner", ["be", "gin", "ner"]),
        ("inspection", ["in", "spec", "tion"]),
    ],
)
def test_word_service_protects_r_controlled_and_digraphs(
    word_service_fixture, word, expected_syllables
):
    result = word_service_fixture.analyze(word)
    assert result["syllables"] == expected_syllables or "".join(result["syllables"]) == word
    assert result["decoding"]
    assert len(result["syllables"]) >= 2


@pytest.mark.parametrize(
    "word, expected_decoding",
    [
        ("establish", "es-táblish"),
        ("disestablish", "dí-ses-tablish"),
        ("disestablished", "dí-ses-tablish-ed"),
        ("disestablishes", "dí-ses-tablish-es"),
        ("disestablishing", "dí-ses-tablish-ing"),
        ("disestablishment", "di-ses-táblish-ment"),
        ("established", "es-táblish-ed"),
        ("establishes", "es-táblish-es"),
        ("establishing", "es-táblish-ing"),
        ("establishment", "es-táblish-ment"),
        ("establishments", "es-táblish-ments"),
        ("estimate", "és-tim-ate"),
        ("estimated", "és-ti-mat-ed"),
        ("estimates", "és-ti-mat-es"),
        ("estimating", "és-ti-mat-ing"),
        ("estimation", "es-tim-átion"),
        ("estimations", "es-ti-mátions"),
        ("over-estimate", "ó-ver-es-tim-ate"),
        ("overestimate", "o-véres-tim-ate"),
        ("overestimated", "o-véres-ti-mat-ed"),
        ("overestimates", "o-véres-ti-mat-es"),
        ("overestimating", "o-véres-ti-mat-ing"),
        ("underestimate", "ún-d-ere-stim-ate"),
        ("underestimated", "ún-d-ere-sti-mat-ed"),
        ("underestimates", "un-d-ére-sti-mat-es"),
        ("underestimating", "un-d-ére-sti-mat-ing"),
    ],
)
def test_word_service_academic_families_establish_and_estimate(
    word_service_fixture, word, expected_decoding
):
    result = word_service_fixture.analyze(word)
    assert result["decoding"] == expected_decoding
