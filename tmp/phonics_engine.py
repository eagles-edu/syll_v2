# app/analysis/phonics_engine.py
from __future__ import annotations

import logging
from typing import List, Optional, Tuple, Set
from app.analysis.reviewed_words import REVIEWED_SYLLABLES
from app.analysis.tracing import trace_event

logger = logging.getLogger(__name__)


class BaseRemoteProvider:
    """Abstract interface for future web scraping additions (Oxford, Longman, etc.)."""
    def fetch_american_syllables(self, word: str) -> Optional[List[str]]:
        raise NotImplementedError


class FutureScraperProxy(BaseRemoteProvider):
    """Designated pass-through endpoint plugin for future selector-based scraping."""
    def __init__(self, fallback_enabled: bool = False):
        self.fallback_enabled = fallback_enabled

    def fetch_american_syllables(self, word: str) -> Optional[List[str]]:
        # Target injection hook for future web scrapers.
        return None


class EslPhonicsEngine:
    vowels = "aeiouy"
    consonant_digraphs = (
        "ch", "sh", "th", "ph", "wh", "ng", "ck", "gh", "kn", "gn",
        "wr", "qu", "dg", "sc",
    )
    vowel_digraphs = (
        "ai", "ay", "ea", "ee", "ei", "ey", "oa", "oe", "oo", "ou",
        "ow", "au", "aw", "ew", "oi", "oy", "ui", "ue", "ie",
    )
    consonant_blends = (
        "bl", "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl",
        "pr", "sk", "sl", "sm", "sn", "sp", "st", "sw", "tr", "tw",
        "scr", "spl", "spr", "str", "shr", "squ", "thr",
    )
    prefixes = (
        "counter", "inter", "intra", "super", "micro", "macro", "psycho",
        "hydro", "mono", "multi", "semi", "anti", "ante", "post", "fore",
        "pre", "pro", "sub", "trans", "auto", "bio", "geo", "tele",
        "con", "com", "suc", "mis", "re", "un", "de", "ex", "in", "po", "be",
    )
    suffixes = (
        "ation", "tion", "sion", "ical", "ious", "ible", "able", "ment",
        "ness", "ward", "wise", "ify", "ize", "ing", "less", "ful", "er",
        "ed", "es", "est", "al", "ion", "ity", "ic", "ian", "ial", "ous",
        "ate", "ly", "en", "or", "ist", "ism", "ual",
    )
    trigraphs = (
        "tch", "dge", "igh", "ind", "ild", "old", "olt", "eigh", "ough",
        "gue", "tion", "sion", "cial", "tial", "thr", "shr", "str",
    )
    r_controlled_patterns = (
        "ar", "er", "ir", "or", "ur", "ear", "eer", "air", "are", "ire",
        "ore", "ure",
    )

    def __init__(self, remote_scraper: Optional[BaseRemoteProvider] = None):
        self.scraper_node = remote_scraper or FutureScraperProxy(fallback_enabled=False)
        self.reviewed_syllables = dict(REVIEWED_SYLLABLES)
        self.local_dictionary: Set[str] = set()
        self._load_system_dictionary()

    def _load_system_dictionary(self) -> None:
        import os
        for path in ("/usr/share/dict/words", "/var/lib/dict/words"):
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    self.local_dictionary.update({line.strip().lower() for line in f if len(line.strip()) > 1})
                return
        self.local_dictionary.update({"sign", "post", "soft", "ware", "hard", "ware", "air", "port"})

    def _resolve_compound_word(self, word: str) -> Optional[List[str]]:
        w_len = len(word)
        if w_len < 5 or word in self.reviewed_syllables:
            return None
        for i in range(3, w_len - 2):
            left, right = word[:i], word[i:]
            if left in self.local_dictionary and right in self.local_dictionary:
                if any(c in self.vowels for c in left) and any(c in self.vowels for c in right):
                    trace_event("CMP-01", "compound_detected", word, [left, right], branch="substring_split_loop")
                    return [left, right]
        return None

    def identify_silent_letters(self, word: str) -> dict[str, list[int]]:
        text = word.lower().strip()
        silent_vowels: set[int] = set()
        silent_consonants: set[int] = set()
        for index, char in enumerate(text):
            if char == "u" and index > 0 and text[index - 1] == "q":
                silent_vowels.add(index)
            if char == "e" and (index == len(text) - 1 or text.endswith("ely") and index == len(text) - 3):
                silent_vowels.add(index)
        for pattern, offset in (("kn", 0), ("gn", 0), ("wr", 0), ("mb", 1), ("pn", 0), ("mn", 0)):
            start = text.find(pattern)
            if start == 0 or (pattern == "mb" and start == len(text) - 2):
                silent_consonants.add(start + offset)
        return {"silent_vowels": sorted(silent_vowels), "silent_consonants": sorted(silent_consonants)}

    def _reduce_affixes(self, word: str) -> tuple[str, list[str], list[str]]:
        remaining = word.lower().strip()
        prefixes: list[str] = []
        suffixes: list[str] = []
        pass_number = 0
        while True:
            pass_number += 1
            changed = False
            for prefix in sorted(self.prefixes, key=len, reverse=True):
                if remaining.startswith(prefix) and len(remaining) > len(prefix) + 2:
                    prefixes.append(prefix)
                    remaining = remaining[len(prefix):]
                    trace_event("AFF-02", "prefix_reduction", word, {"prefix": prefix, "remaining": remaining})
                    changed = True
                    break
            if not changed:
                for suffix in sorted(self.suffixes, key=len, reverse=True):
                    if remaining.endswith(suffix) and len(remaining) > len(suffix) + 2:
                        suffixes.insert(0, suffix)
                        remaining = remaining[:-len(suffix)]
                        trace_event("AFF-01", "suffix_reduction", word, {"suffix": suffix, "remaining": remaining})
                        changed = True
                        break
            if not changed:
                trace_event("AFF-06", "affix_reduction_decision", remaining, "no_further_reduction")
                return remaining, prefixes, suffixes

    def _boundary_between_nuclei(self, text: str, previous_nucleus: tuple[int, int], next_start: int) -> int:
        previous_start, previous_end = previous_nucleus
        between = text[previous_end:next_start]
        if not between:
            return next_start
        protected = next((u for u in sorted(self.consonant_digraphs + self.trigraphs, key=len, reverse=True) if between.endswith(u)), None)
        if protected:
            return next_start - len(protected)
        if len(between) == 1:
            long_vowel = text[previous_start:previous_end] in self.vowel_digraphs
            return previous_end if long_vowel else next_start - 1
        if len(between) == 2 and between == between:
            return next_start - 1
        known_blend = next((b for b in sorted(self.consonant_blends, key=len, reverse=True) if between.endswith(b)), None)
        if known_blend and len(between) > len(known_blend):
            return next_start - len(known_blend)
        return previous_end + 1

    def _detect_nuclei(self, text: str, target_vowel_count: int = 0) -> list[tuple[int, int]]:
        del target_vowel_count
        silent = self.identify_silent_letters(text)["silent_vowels"]
        vowel_units = ("eau", "igh", "eigh", "ough", "air", "ear", "eer", "ure", "are", "ire", "ore") + self.vowel_digraphs
        nuclei: list[tuple[int, int]] = []
        index = 0
        while index < len(text):
            if index in silent or text[index:index + 2] == "qu":
                index += 1 if index in silent else 2
                continue
            unit = next((c for c in sorted(vowel_units, key=len, reverse=True) if text.startswith(c, index)), None)
            if unit:
                nuclei.append((index, index + len(unit)))
                index += len(unit)
            elif text[index] in self.vowels:
                nuclei.append((index, index + 1))
                index += 1
            else:
                index += 1
        return nuclei

    @staticmethod
    def _chunks_from_boundaries(text: str, boundaries: list[int]) -> list[str]:
        chunks: list[str] = []
        start = 0
        for boundary in sorted(list(set(boundaries))):
            chunks.append(text[start:boundary])
            start = boundary
        chunks.append(text[start:])
        return chunks

    def _generic_split(self, word: str, target_vowel_count: int = 0) -> List[str]:
        text = word.lower().strip()
        remaining, prefixes, suffixes = self._reduce_affixes(text)
        if prefixes or suffixes:
            core_parts = self._generic_split(remaining, target_vowel_count)
            return prefixes + core_parts + suffixes
        nuclei = self._detect_nuclei(text, target_vowel_count)
        if len(nuclei) < 2:
            return [text] if text else []
        boundaries = [self._boundary_between_nuclei(text, prev, nxt_start) for prev, (nxt_start, _) in zip(nuclei, nuclei[1:])]
        chunks = self._chunks_from_boundaries(text, boundaries)
        return [c for c in chunks if c]

    def split_syllables(self, word: str, target_vowel_count: int = 0) -> List[str]:
        text = word.lower().strip()
        if not text:
            return []
        if "-" in text and not text.startswith("-") and not text.endswith("-"):
            return text.split("-")
        if text in self.reviewed_syllables:
            return list(self.reviewed_syllables[text])
        compound_parts = self._resolve_compound_word(text)
        if compound_parts:
            return [chunk for part in compound_parts for chunk in self.split_syllables(part, target_vowel_count)]
        scraped_result = self.scraper_node.fetch_american_syllables(text)
        if scraped_result:
            return scraped_result
        if text.endswith("ckle") and len(text) > 5:
            return [text[:-2], "le"]
        if text.endswith("le") and len(text) > 2 and text[-3] not in self.vowels:
            return [text[:-3], text[-3:]]
        return self._generic_split(text, target_vowel_count)

    def evaluate_accent_index(self, word: str, chunks: List[str]) -> int:
        """Return a deterministic spelling-based stress fallback."""
        if len(chunks) <= 1:
            return 0
        if word.endswith(("tally", "ally")) or word.endswith("ly"):
            return max(0, len(chunks) - 2)
        for suffix in (
            "tional", "tial", "cial", "sion", "tion", "ity", "ic",
            "ical", "ian", "ial", "ious",
        ):
            if word.endswith(suffix):
                return max(0, len(chunks) - 2)
        if chunks[0] in {"de", "re", "ex", "in", "po", "pro", "be"}:
            return min(1, len(chunks) - 1)
        return 0

    def phonics_inventory(self) -> dict[str, object]:
        """Expose the controlled rule catalog used by this engine."""
        return {
            "consonant_digraphs": list(self.consonant_digraphs),
            "vowel_digraphs": list(self.vowel_digraphs),
            "consonant_blends": list(self.consonant_blends),
            "r_controlled_vowels": list(self.r_controlled_patterns),
            "prefixes": list(self.prefixes),
            "suffixes": list(self.suffixes),
            "trigraphs": list(self.trigraphs),
        }
