"""Pronunciation and spelling analysis components."""

from app.analysis.phonics_engine import EslPhonicsEngine
from app.analysis.pronunciation import CmuPronunciationService
from app.analysis.reviewed_words import REVIEWED_STRESS_INDEX, REVIEWED_SYLLABLES
from app.analysis.compound import CompoundResolver

__all__ = [
    "EslPhonicsEngine", "CmuPronunciationService", "CompoundResolver", "REVIEWED_SYLLABLES", "REVIEWED_STRESS_INDEX",
]
