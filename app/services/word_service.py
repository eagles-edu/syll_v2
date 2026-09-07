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
    EslPhonicsEngine,
    REVIEWED_STRESS_INDEX,
    REVIEWED_SYLLABLES,
)
from app.config import settings
from app.repositories import WordBankRepository
from app.services.word_bank_io import WordBankIO
from app.analysis.tracing import begin_analysis_trace, end_analysis_trace, set_trace_result, trace_event


logger = logging.getLogger(__name__)


class WordAnalysisService:
    """Coordinate DB-first lookup and deterministic word analysis."""

    _engine = EslPhonicsEngine()
    _cmudict: dict | None = None

    def __init__(
        self,
        db_path: str | None = None,
        use_word_bank: bool = False,
        skip_word_bank_words: set[str] | None = None,
        bypass_cache: bool | None = None,
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
                {
                    "hit": saved is not None,
                    "branch": (
                        "bypass_override_active"
                        if self.bypass_cache
                        else "lookup_result"
                    ),
                },
            )
            logger.debug(
                "analysis word_bank word=%r enabled=%s skipped=%s hit=%s",
                cleaned,
                self.use_word_bank,
                cleaned in self.skip_word_bank_words,
                saved is not None,
            )
            if saved is not None:
                saved["source"] = "word-bank"
                trace_event("OUT-01", "analysis_result", "word-bank", saved)
                set_trace_result(saved)
                logger.debug("analysis complete word=%r result=%r", cleaned, saved)
                return saved

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
            result = {
            "word": cleaned,
            "normalized_word": cleaned,
            "syllables": chunks,
            "stressed_syllable_index": stress_index,
            "decoding": decoding,
            "formatted": decoding,
            "cefr": cefr,
            "source": "rule-based",
            "from_word_bank": False,
            "is_academic": cefr in {"B1", "B2", "C1", "C2"},
            }
            trace_event("OUT-01", "analysis_result", chunks, result)
            set_trace_result(result)
            logger.debug("analysis complete word=%r result=%r", cleaned, result)
            return result
        finally:
            end_analysis_trace(trace_token)

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
