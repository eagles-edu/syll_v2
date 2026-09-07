"""Public word-analysis service façade.

The façade preserves the original import and method contract while delegating
phonics, pronunciation, persistence, and file-format concerns to focused
modules.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.analysis import (
    CmuPronunciationService,
    CompoundResolver,
    EslPhonicsEngine,
    REVIEWED_STRESS_INDEX,
    REVIEWED_SYLLABLES,
)
from app.config import settings
from app.providers import MerriamWebsterProvider, MerriamWebsterResult
from app.repositories import WordBankRepository
from app.services.word_bank_io import WordBankIO
from app.analysis.tracing import begin_analysis_trace, end_analysis_trace, set_trace_result, trace_event


logger = logging.getLogger(__name__)


class WordAnalysisService:
    """Coordinate DB-first lookup and deterministic word analysis."""

    _engine = EslPhonicsEngine()
    _cmudict: dict | None = None

    def __init__(  # pylint: disable=too-many-positional-arguments
        self,
        db_path: str | None = None,
        use_word_bank: bool = False,
        skip_word_bank_words: set[str] | None = None,
        bypass_cache: bool | None = None,
        mw_provider: MerriamWebsterProvider | None = None,
        compound_resolver: CompoundResolver | None = None,
    ):
        self.db_path = db_path or settings.database_path
        self.use_word_bank = use_word_bank
        self.bypass_cache = bypass_cache if bypass_cache is not None else settings.debug
        self.skip_word_bank_words = {
            self._normalize_word(word) for word in (skip_word_bank_words or set())
        }
        if self.bypass_cache:
            logger.info("🔧 Dev Mode Active: Cache bypassed.")
        self.repository = WordBankRepository(self.db_path)
        self._seed_reviewed_word_bank()
        self.io = WordBankIO(self.save_word, self.list_saved_words)
        self.mw_provider = mw_provider or MerriamWebsterProvider(
            api_key=settings.merriam_webster_api_key,
            base_url=settings.merriam_webster_base_url,
            timeout_seconds=settings.merriam_webster_timeout_seconds,
        )
        self.compound_resolver = compound_resolver or CompoundResolver(
            CmuPronunciationService.pronunciation,
            lexicon_path=settings.compound_lexicon_path,
        )

    def _seed_reviewed_word_bank(self) -> None:
        """Persist reviewed exceptions so later analysis is always DB-first."""
        for word, syllables in REVIEWED_SYLLABLES.items():
            existing = self.repository.lookup(word)
            if existing is not None and existing.get("source") not in {"reviewed", "rule-based"}:
                continue
            pronunciation = CmuPronunciationService.pronunciation(word)
            stress_index = REVIEWED_STRESS_INDEX.get(word)
            if stress_index is None:
                stress_index = (
                    CmuPronunciationService.stress_index(pronunciation, syllables)
                    if pronunciation
                    else self._engine.evaluate_accent_index(word, syllables)
                )
            decoding = self._add_stress_marker(syllables, stress_index)
            cefr = self._calculate_cefr(word)
            self.repository.save({
                "word": word,
                "normalized_word": word,
                "syllables": list(syllables),
                "stressed_syllable_index": stress_index,
                "decoding": decoding,
                "formatted": decoding,
                "cefr": cefr,
                "source": "reviewed",
                "is_academic": cefr in {"B1", "B2", "C1", "C2"},
                "pos": None,
                "family": None,
                "notes": "Reviewed phonics exception.",
            })

    @classmethod
    def _load_cmu_dict(cls) -> dict:
        cls._cmudict = CmuPronunciationService.dictionary()
        return cls._cmudict

    @staticmethod
    def _normalize_word(word: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z'-]", "", str(word)).strip().lower()
        if not cleaned:
            raise ValueError("Word input is required.")
        return cleaned

    @classmethod
    def _get_cmu_stress_syllable_index(cls, phonemes: list[str], chunks: list[str]) -> int:
        return CmuPronunciationService.stress_index(phonemes, chunks)

    @classmethod
    def _count_cmu_vowel_sounds(cls, word: str) -> int:
        return CmuPronunciationService.vowel_count(word)

    def count_vowel_sounds(self, word: str) -> int:
        return self._count_cmu_vowel_sounds(self._normalize_word(word))

    def identify_silent_letters(self, word: str) -> dict[str, list[int]]:
        return self._engine.identify_silent_letters(self._normalize_word(word))

    def phonics_inventory(self) -> dict[str, object]:
        return self._engine.phonics_inventory()

    @staticmethod
    def _normalize_bulk_words(raw: Any) -> list[str]:
        if raw is None:
            raise ValueError("At least one word is required.")
        if isinstance(raw, dict):
            for key in ("words", "text", "input", "word"):
                if key in raw and raw[key] is not None:
                    raw = raw[key]
                    break
            else:
                raise ValueError("Bulk input must include 'words', 'text', 'input', or 'word'.")
        if isinstance(raw, str):
            candidates = [item for item in re.split(r"[\r\n,;\t\s]+", raw) if item.strip()]
        elif isinstance(raw, (list, tuple, set)):
            candidates = []
            for item in raw:
                if item is None:
                    continue
                candidates.extend(re.split(r"[\r\n,;\t\s]+", str(item)))
        else:
            raise TypeError("Bulk input must be a list of words or newline-delimited text.")
        result = []
        seen = set()
        for candidate in candidates:
            cleaned = candidate.strip()
            if not cleaned:
                continue
            word = WordAnalysisService._normalize_word(cleaned)
            if word not in seen:
                seen.add(word)
                result.append(word)
        if not result:
            raise ValueError("At least one word is required.")
        return result

    @staticmethod
    def _add_stress_marker(syllables: list[str], stressed_index: int) -> str:
        if not syllables:
            return ""
        index = stressed_index if 0 <= stressed_index < len(syllables) else 0
        accents = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú", "y": "ý"}
        marked = [syllable.lower() for syllable in syllables]
        chars = list(marked[index])
        for position, char in enumerate(chars):
            if char == "u" and position > 0 and chars[position - 1] == "q":
                continue
            if char in accents:
                chars[position] = accents[char]
                break
        marked[index] = "".join(chars)
        return "-".join(marked)

    @staticmethod
    def _calculate_cefr(word: str) -> str:
        length = len(word)
        if length <= 3:
            return "A1"
        if length <= 5:
            return "A2"
        if length <= 8:
            return "B1"
        if length <= 10:
            return "B2"
        if length <= 12:
            return "C1"
        return "C2"

    def lookup_word(self, word: str) -> dict[str, Any] | None:
        return self.repository.lookup(self._normalize_word(word))

    def list_saved_words(self) -> list[dict[str, Any]]:
        return self.repository.list_words()

    def analyze(self, word: str) -> dict[str, object]:
        """Analyze one word through validated provider and deterministic local paths."""
        cleaned = self._normalize_word(word)
        trace_token = begin_analysis_trace(cleaned)
        try:
            logger.debug("analysis start raw=%r normalized=%r", word, cleaned)
            word_bank_allowed = (
                self.use_word_bank
                and not self.bypass_cache
                and cleaned not in self.skip_word_bank_words
            )
            saved = self.repository.lookup(cleaned) if word_bank_allowed else None
            trace_event(
                "WB-01",
                "word_bank_lookup",
                {
                    "enabled": self.use_word_bank,
                    "bypassed_via_dev_switch": self.bypass_cache,
                    "skipped": cleaned in self.skip_word_bank_words,
                },
                {"hit": saved is not None, "source": saved.get("source") if saved else None},
            )
            logger.debug(
                "analysis word_bank word=%r enabled=%s skipped=%s hit=%s",
                cleaned,
                self.use_word_bank,
                cleaned in self.skip_word_bank_words,
                saved is not None,
            )
            if saved is not None and saved.get("source") == "merriam-webster":
                trace_event("OUT-01", "analysis_result", "merriam-webster-cache", saved)
                set_trace_result(saved)
                return saved

            provider_result = self.mw_provider.lookup(cleaned)
            local_result = self._analyze_local(cleaned)
            if provider_result is not None:
                result = self._result_from_mw(provider_result, local_result)
                if self._candidate_differs(provider_result, local_result):
                    self._record_disagreement(cleaned, provider_result, local_result, result)
                if word_bank_allowed:
                    result = self.repository.save(self._record_for_repository(result))
                result["source"] = "merriam-webster"
                result["from_word_bank"] = word_bank_allowed
            elif saved is not None:
                saved["source"] = "word-bank"
                result = saved
            else:
                result = local_result
            trace_event("OUT-01", "analysis_result", result.get("source"), result)
            set_trace_result(result)
            logger.debug("analysis complete word=%r result=%r", cleaned, result)
            return result
        finally:
            end_analysis_trace(trace_token)

    def _analyze_local(self, cleaned: str) -> dict[str, object]:
        pronunciation = CmuPronunciationService.pronunciation(cleaned)
        vowel_count = CmuPronunciationService.vowel_count(cleaned)
        trace_event("PR-01", "pronunciation_vowel_count", pronunciation, vowel_count)
        logger.debug(
            "analysis pronunciation word=%r phones=%r vowel_count=%d",
            cleaned,
            pronunciation,
            vowel_count,
        )
        chunks = self._engine.split_syllables(cleaned, vowel_count) or [cleaned]
        compound = (
            None
            if cleaned in REVIEWED_SYLLABLES or not self._compound_needed(chunks, vowel_count)
            else self.compound_resolver.resolve(cleaned)
        )
        if compound:
            chunks = compound
            source = "compound"
            trace_event("SY-01", "syllable_assembly", "compound", chunks)
        else:
            source = "rule-based"
            trace_event("SY-01", "syllable_assembly", vowel_count, chunks)
        logger.debug("analysis syllables word=%r chunks=%r", cleaned, chunks)
        stress_index = REVIEWED_STRESS_INDEX.get(cleaned)
        if stress_index is None:
            stress_index = (
                self._get_cmu_stress_syllable_index(pronunciation, chunks)
                if pronunciation
                else self._engine.evaluate_accent_index(cleaned, chunks)
            )
        stress_index = min(max(stress_index, 0), len(chunks) - 1)
        trace_event("ST-01", "stress_decision", pronunciation or "fallback", stress_index)
        logger.debug(
            "analysis stress word=%r index=%d method=%s",
            cleaned,
            stress_index,
            "cmudict" if pronunciation else "spelling-fallback",
        )
        decoding = self._add_stress_marker(chunks, stress_index)
        cefr = self._calculate_cefr(cleaned)
        return {
            "word": cleaned,
            "normalized_word": cleaned,
            "syllables": list(chunks),
            "stressed_syllable_index": stress_index,
            "decoding": decoding,
            "formatted": decoding,
            "cefr": cefr,
            "source": source,
            "from_word_bank": False,
            "is_academic": cefr in {"B1", "B2", "C1", "C2"},
        }

    @classmethod
    def _compound_needed(cls, chunks: list[str], vowel_count: int) -> bool:
        """Only invoke compound inference when the normal path needs repair."""
        if not vowel_count or len(chunks) != vowel_count:
            return True
        protected_onsets = cls._engine.consonant_digraphs + cls._engine.trigraphs
        return any(
            any(chunk.startswith(unit) for unit in protected_onsets)
            for chunk in chunks[1:]
        )

    def _result_from_mw(
        self,
        provider_result: MerriamWebsterResult,
        local_result: dict[str, object],
    ) -> dict[str, object]:
        chunks = list(provider_result.syllables)
        stress_index = provider_result.stress_index
        if stress_index is None:
            stress_index = self._get_cmu_stress_syllable_index(
                CmuPronunciationService.pronunciation(provider_result.word), chunks
            )
        if stress_index is None:
            stress_index = int(local_result.get("stressed_syllable_index", 0))
        stress_index = min(max(stress_index, 0), len(chunks) - 1)
        decoding = self._add_stress_marker(chunks, stress_index)
        cefr = self._calculate_cefr(provider_result.word)
        return {
            "word": provider_result.word,
            "normalized_word": provider_result.word,
            "syllables": chunks,
            "stressed_syllable_index": stress_index,
            "decoding": decoding,
            "formatted": decoding,
            "cefr": cefr,
            "source": provider_result.source,
            "from_word_bank": False,
            "is_academic": cefr in {"B1", "B2", "C1", "C2"},
        }

    @staticmethod
    def _candidate_differs(provider_result: MerriamWebsterResult, local_result: dict[str, object]) -> bool:
        return (
            list(provider_result.syllables) != local_result.get("syllables")
            or provider_result.stress_index is not None
            and provider_result.stress_index != local_result.get("stressed_syllable_index")
        )

    def _record_disagreement(
        self,
        word: str,
        provider_result: MerriamWebsterResult,
        local_result: dict[str, object],
        selected: dict[str, object],
    ) -> None:
        payload = {
            "algorithm_version": "2",
            "word": word,
            "local": {
                "source": local_result.get("source"),
                "syllables": local_result.get("syllables"),
                "stressed_syllable_index": local_result.get("stressed_syllable_index"),
            },
            "mw": {
                "source": provider_result.source,
                "syllables": list(provider_result.syllables),
                "pronunciation": provider_result.pronunciation,
                "stress_index": provider_result.stress_index,
            },
            "selected": {
                "source": selected.get("source"),
                "syllables": selected.get("syllables"),
                "stressed_syllable_index": selected.get("stressed_syllable_index"),
            },
            "decision": "merriam_webster_authoritative",
            "cache_provider_status": "validated_response",
        }
        trace_event("MW-04", "provider_disagreement", payload, "merriam-webster")
        logger.info(
            "logic_disagreement word=%r decision=merriam_webster_authoritative",
            word,
            extra={"logic_disagreement": payload},
        )

    @staticmethod
    def _record_for_repository(result: dict[str, object]) -> dict[str, object]:
        return {
            "word": result["word"],
            "normalized_word": result["normalized_word"],
            "syllables": result["syllables"],
            "stressed_syllable_index": result["stressed_syllable_index"],
            "decoding": result["decoding"],
            "formatted": result["formatted"],
            "cefr": result["cefr"],
            "source": result["source"],
            "is_academic": result["is_academic"],
            "pos": None,
            "family": None,
            "notes": "Validated Merriam-Webster syllable boundary.",
        }

    def analyze_batch(self, raw: Any) -> list[dict[str, object]]:
        return [self.analyze(word) for word in self._normalize_bulk_words(raw)]

    def analyze_many(self, raw: Any) -> list[dict[str, object]]:
        return self.analyze_batch(raw)

    bulk_analyze = analyze_batch

    def build_word_bank_record(self, word: str) -> dict[str, object]:
        result = self.analyze(word)
        return {
            "word": result["word"], "normalized_word": result["normalized_word"],
            "formatted": result["formatted"], "decoding": result["decoding"],
            "syllables": result["syllables"],
            "stressed_syllable_index": result["stressed_syllable_index"],
            "cefr": result["cefr"], "family": None, "source": result.get("source", "rule-based"),
            "is_academic": bool(result.get("is_academic", False)), "pos": None, "notes": None,
        }

    def save_word(
        self,
        word: str,
        *,
        syllables: list[str] | None = None,
        decoding: str | None = None,
        pos: str | None = None,
        family: str | None = None,
        is_academic: bool | None = None,
        notes: str | None = None,
        source: str = "user",
        stress_index: int | None = None,
    ) -> dict[str, Any]:
        cleaned = self._normalize_word(word)
        base = self.lookup_word(cleaned) or self.build_word_bank_record(cleaned)
        selected_syllables = syllables if syllables is not None else base.get("syllables")
        if not isinstance(selected_syllables, list) or not all(isinstance(item, str) for item in selected_syllables):
            raise ValueError("Saved word syllables must be a list of strings.")
        selected_decoding = decoding if decoding is not None else base.get("decoding")
        if not isinstance(selected_decoding, str):
            raise ValueError("Saved word decoding must be text.")
        selected_stress = stress_index if stress_index is not None else base.get("stressed_syllable_index")
        if not isinstance(selected_stress, int):
            raise ValueError("Saved word stress index must be an integer.")
        record = {
            "word": cleaned, "normalized_word": cleaned, "syllables": selected_syllables,
            "stressed_syllable_index": selected_stress, "decoding": selected_decoding,
            "formatted": selected_decoding or "-".join(selected_syllables),
            "cefr": base.get("cefr", self._calculate_cefr(cleaned)), "source": source,
            "is_academic": bool(base.get("is_academic", False)) if is_academic is None else is_academic,
            "pos": pos or base.get("pos"), "family": family or base.get("family"),
            "notes": notes or base.get("notes"),
        }
        saved = self.repository.save(record)
        saved["source"] = source
        return saved

    def import_word_bank(self, payload: Any, filename: str | None = None) -> dict[str, Any]:
        return self.io.import_payload(payload, filename)

    def export_word_bank(self, format_name: str = "csv") -> dict[str, Any]:
        return self.io.export(format_name)

    @staticmethod
    def _clean_word_from_data(value: Any) -> str:
        if value is None:
            raise ValueError("Word value is required.")
        return WordAnalysisService._normalize_word(str(value))

    @staticmethod
    def _split_family_name(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value).strip()


__all__ = ["WordAnalysisService"]
