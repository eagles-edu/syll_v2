"""Evidence-backed compound-word resolution."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable

from app.analysis.tracing import trace_event


logger = logging.getLogger(__name__)
_WORD_ENTRY_RE = re.compile(r"^[a-zA-Z]+$")
_MORPHEME_ONLY_PARTS = frozenset({
    "able", "age", "al", "ally", "ate", "ed", "er", "es", "est", "ful", "ible",
    "ic", "ing", "ion", "ise", "ism", "ist", "ive", "ize", "ly", "ment", "ness",
    "ous", "ship", "tion", "y", "dis", "in", "inter", "mis", "over", "pre", "re",
    "sub", "trans", "un", "under",
})


class CompoundResolver:
    """Resolve bounded compound components without guessing from spelling alone."""

    def __init__(
        self,
        pronunciation: Callable[[str], list[str] | None],
        lexicon_path: str | Path = "/usr/share/dict/words",
        max_depth: int = 4,
        minimum_component_length: int = 3,
    ):
        self._pronunciation = pronunciation
        self.lexicon_path = Path(lexicon_path)
        self.max_depth = max(1, max_depth)
        self.minimum_component_length = max(2, minimum_component_length)
        self._lexicon: frozenset[str] | None = None

    @property
    def lexicon(self) -> frozenset[str]:
        if self._lexicon is None:
            words: set[str] = set()
            try:
                words.update(
                    line.strip().lower()
                    for line in self.lexicon_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                    if line.strip() == line.strip().lower()
                    and _WORD_ENTRY_RE.fullmatch(line.strip())
                )
            except OSError:
                logger.info("compound_lexicon_unavailable path=%s", self.lexicon_path)
            self._lexicon = frozenset(words)
            trace_event("CMP-01", "compound_lexicon_load", str(self.lexicon_path), {"count": len(words)})
        return self._lexicon

    def resolve(self, word: str) -> list[str] | None:
        """Return deterministic compound parts only when every part has CMU evidence."""
        normalized = word.lower().strip()
        result = self._resolve(normalized, depth=0, active=frozenset())
        trace_event(
            "CMP-05",
            "compound_resolution",
            normalized,
            result or [normalized],
            resolution="apply" if result else "fallback",
        )
        return result

    def _resolve(self, word: str, depth: int, active: frozenset[str]) -> list[str] | None:
        if depth >= self.max_depth or word in active or not _WORD_ENTRY_RE.fullmatch(word):
            trace_event(
                "CMP-02",
                "compound_guard",
                word,
                {"depth": depth, "max_depth": self.max_depth},
                resolution="fallback",
            )
            return None
        candidates = self._candidates(word)
        for left, right in candidates:
            left_parts = self._resolve(left, depth + 1, active | {word}) or [left]
            right_parts = self._resolve(right, depth + 1, active | {word}) or [right]
            combined = left_parts + right_parts
            if all(self._has_cmu_evidence(part) for part in combined) and "".join(combined) == word:
                trace_event("CMP-03", "compound_candidate", word, combined, branch="substring_split_loop")
                return combined
        return None

    def _candidates(self, word: str) -> list[tuple[str, str]]:
        candidates: list[tuple[tuple[int, int, int], tuple[str, str]]] = []
        lower_bound = self.minimum_component_length
        upper_bound = len(word) - self.minimum_component_length
        for boundary in range(lower_bound, upper_bound + 1):
            left, right = word[:boundary], word[boundary:]
            if not self._is_component(left) or not self._is_component(right):
                continue
            whole_count = _vowel_count(self._pronunciation(word))
            component_count = (
                _vowel_count(self._pronunciation(left))
                + _vowel_count(self._pronunciation(right))
            )
            score = (
                int(whole_count > 0 and whole_count == component_count),
                min(len(left), len(right)),
                -abs(len(left) - len(right)),
            )
            candidates.append((score, (left, right)))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [candidate for _, candidate in candidates]

    def _is_component(self, word: str) -> bool:
        return (
            word not in _MORPHEME_ONLY_PARTS
            and (not self.lexicon or word in self.lexicon)
            and self._has_cmu_evidence(word)
        )

    def _has_cmu_evidence(self, word: str) -> bool:
        pronunciation = self._pronunciation(word)
        return bool(pronunciation and _vowel_count(pronunciation) > 0)


def _vowel_count(pronunciation: list[str] | None) -> int:
    if not pronunciation:
        return 0
    return sum(
        bool(
            re.search(
                r"(?:AA|AE|AH|AO|AW|AY|EH|ER|EY|IH|IY|OW|OY|UH|UW)\d?$",
                phone,
            )
        )
        for phone in pronunciation
    )


__all__ = ["CompoundResolver"]
