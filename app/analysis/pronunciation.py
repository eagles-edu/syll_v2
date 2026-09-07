"""CMU pronunciation loading and stress mapping."""

from __future__ import annotations

import re
from typing import Iterable

import nltk
from nltk.corpus import cmudict


class CmuPronunciationService:
    """Load CMUdict once and translate primary stress to spelling chunks."""

    vowel_phones = frozenset({
        "AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH",
        "IY", "OW", "OY", "UH", "UW",
    })
    _dictionary: dict | None = None

    @classmethod
    def dictionary(cls) -> dict:
        if cls._dictionary is None:
            try:
                nltk.data.find("corpora/cmudict")
            except LookupError:
                nltk.download("cmudict", quiet=True)
            cls._dictionary = cmudict.dict()
        return cls._dictionary

    @classmethod
    def pronunciation(cls, word: str) -> list[str] | None:
        entries = cls.dictionary().get(word.lower().strip())
        return entries[0] if entries else None

    @classmethod
    def vowel_count(cls, word: str) -> int:
        pronunciation = cls.pronunciation(word)
        if not pronunciation:
            return 0
        return sum(cls._base_phone(phone) in cls.vowel_phones for phone in pronunciation)

    @classmethod
    def stress_index(cls, phonemes: Iterable[str], chunks: list[str]) -> int:
        phones = list(phonemes)
        stressed_phone = next((index for index, phone in enumerate(phones) if phone.endswith("1")), 0)
        vowel_positions = [
            index for index, phone in enumerate(phones)
            if cls._base_phone(phone) in cls.vowel_phones
        ]
        if not vowel_positions or not chunks:
            return 0
        stress_vowel = sum(position < stressed_phone for position in vowel_positions)
        chunk_vowel_counts = [cls._spelling_vowel_count(chunk) for chunk in chunks]
        if len(chunks) == len(vowel_positions) and sum(chunk_vowel_counts) == len(vowel_positions):
            return min(stress_vowel, len(chunks) - 1)
        cumulative = 0
        for index, count in enumerate(chunk_vowel_counts):
            if stress_vowel < cumulative + count:
                return index
            cumulative += count
        return len(chunks) - 1

    @staticmethod
    def _spelling_vowel_count(chunk: str) -> int:
        count = 0
        in_run = False
        for index, char in enumerate(chunk.lower()):
            if char == "u" and index > 0 and chunk[index - 1].lower() == "q":
                in_run = False
                continue
            if char in "aeiouy":
                if not in_run:
                    count += 1
                in_run = True
            else:
                in_run = False
        return max(1, count)

    @staticmethod
    def _base_phone(phone: str) -> str:
        return re.sub(r"\d$", "", phone)


__all__ = ["CmuPronunciationService"]
