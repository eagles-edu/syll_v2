python3 -c "
import os

files = {
    'app/services/word_service.py': '''from __future__ import annotations
import logging
import re
from typing import Any
from app.analysis import CmuPronunciationService, EslPhonicsEngine, REVIEWED_STRESS_INDEX, REVIEWED_SYLLABLES
from app.config import settings
from app.repositories import WordBankRepository
from app.services.word_bank_io import WordBankIO
from app.analysis.tracing import begin_analysis_trace, end_analysis_trace, set_trace_result, trace_event

logger = logging.getLogger(__name__)

class WordAnalysisService:
    _engine = EslPhonicsEngine()
    _cmudict: dict | None = None

    def __init__(self, db_path: str | None = None, use_word_bank: bool = False, skip_word_bank_words: set[str] | None = None, bypass_cache: bool | None = None):
        self.db_path = db_path or settings.database_path
        self.use_word_bank = use_word_bank
        self.skip_word_bank_words = {self._normalize_word(word) for word in (skip_word_bank_words or set())}
        self.bypass_cache = bypass_cache if bypass_cache is not None else settings.debug
        if self.bypass_cache:
            logger.info('🔧 Dev Mode Active: Cache bypassed.')
        self.repository = WordBankRepository(self.db_path)
        self._seed_reviewed_word_bank()
        self.io = WordBankIO(self.save_word, self.list_saved_words)

    def _seed_reviewed_word_bank(self) -> None:
        for word, syllables in REVIEWED_SYLLABLES.items():
            existing = self.repository.lookup(word)
            if existing is not None and existing.get('source') not in {'reviewed', 'rule-based'}:
                continue
            pronunciation = CmuPronunciationService.pronunciation(word)
            stress_index = REVIEWED_STRESS_INDEX.get(word)
            if stress_index is None:
                stress_index = CmuPronunciationService.stress_index(pronunciation, syllables) if pronunciation else self._engine.evaluate_accent_index(word, syllables)
            decoding = self._add_stress_marker(syllables, stress_index)
            self.repository.save({
                'word': word, 'normalized_word': word, 'syllables': list(syllables),
                'stressed_syllable_index': stress_index, 'decoding': decoding, 'formatted': decoding,
                'cefr': self._calculate_cefr(word), 'source': 'reviewed', 'is_academic': self._calculate_cefr(word) in {'B1', 'B2', 'C1', 'C2'}
            })

    @staticmethod
    def _normalize_word(word: str) -> str:
        cleaned = re.sub(r'[^a-zA-Z\'-]', '', str(word)).strip().lower()
        if not cleaned: raise ValueError('Word input is required.')
        return cleaned

    def analyze(self, word: str) -> dict[str, object]:
        cleaned = self._normalize_word(word)
        trace_token = begin_analysis_trace(cleaned)
        try:
            word_bank_allowed = self.use_word_bank and not self.bypass_cache and cleaned not in self.skip_word_bank_words
            saved = self.repository.lookup(cleaned) if word_bank_allowed else None
            if saved is not None:
                saved['source'] = 'word-bank'
                set_trace_result(saved)
                return saved
            pronunciation = CmuPronunciationService.pronunciation(cleaned)
            vowel_count = CmuPronunciationService.vowel_count(cleaned)
            chunks = self._engine.split_syllables(cleaned, vowel_count) or [cleaned]
            stress_index = REVIEWED_STRESS_INDEX.get(cleaned)
            if stress_index is None:
                stress_index = CmuPronunciationService.stress_index(pronunciation, chunks) if pronunciation else self._engine.evaluate_accent_index(cleaned, chunks)
            stress_index = min(max(stress_index, 0), len(chunks) - 1)
            decoding = self._add_stress_marker(chunks, stress_index)
            cefr = self._calculate_cefr(cleaned)
            result = {'word': cleaned, 'normalized_word': cleaned, 'syllables': chunks, 'stressed_syllable_index': stress_index, 'decoding': decoding, 'formatted': decoding, 'cefr': cefr, 'source': 'rule-based', 'from_word_bank': False, 'is_academic': cefr in {'B1', 'B2', 'C1', 'C2'}}
            if self.use_word_bank and not self.bypass_cache:
                self.repository.save({**result, 'source': 'rule-based'})
            set_trace_result(result)
            return result
        finally:
            end_analysis_trace(trace_token)

    @staticmethod
    def _add_stress_marker(syllables: list[str], stressed_index: int) -> str:
        if not syllables: return ''
        index = stressed_index if 0 <= stressed_index < len(syllables) else 0
        accents = {'a': 'á', 'e': 'é', 'i': 'í', 'o': 'ó', 'u': 'ú', 'y': 'ý'}
        marked = [s.lower() for s in syllables]
        chars = list(marked[index])
        for p, c in enumerate(chars):
            if c == 'u' and p > 0 and chars[p - 1] == 'q': continue
            if c in accents:
                chars[p] = accents[c]
                break
        marked[index] = ''.join(chars)
        return '-'.join(marked)

    @staticmethod
    def _calculate_cefr(word: str) -> str:
        length = len(word)
        if length <= 3: return 'A1'
        if length <= 5: return 'A2'
        if length <= 8: return 'B1'
        if length <= 10: return 'B2'
        if length <= 12: return 'C1'
        return 'C2'

    def analyze_batch(self, raw: Any) -> list[dict[str, object]]:
        return [self.analyze(w) for w in self._normalize_bulk_words(raw)]

    @staticmethod
    def _normalize_bulk_words(raw: Any) -> list[str]:
        if raw is None: raise ValueError('At least one word is required.')
        if isinstance(raw, dict):
            for key in ('words', 'text', 'input', 'word'):
                if key in raw and raw[key] is not None:
                    raw = raw[key]
                    break
        if isinstance(raw, str):
            candidates = [item for item in re.split(r'[\r\n,;\t\s]+', raw) if item.strip()]
        elif isinstance(raw, (list, tuple, set)):
            candidates = [str(item) for item in raw if item is not None]
        result = []
        seen = set()
        for c in candidates:
            w = WordAnalysisService._normalize_word(c.strip())
            if w not in seen:
                seen.add(w)
                result.append(w)
        return result

    def lookup_word(self, word: str) -> dict[str, Any] | None: return self.repository.lookup(self._normalize_word(word))
    def list_saved_words(self) -> list[dict[str, Any]]: return self.repository.list_words()
    def save_word(self, word: str, **kwargs) -> dict[str, Any]: return self.repository.save({'word': word, 'normalized_word': word, **kwargs})''',

    'tests/test_word_service.py': '''import unittest
from app.analysis.phonics_engine import EslPhonicsEngine

class TestEslPhonicsEngineRegressions(unittest.TestCase):
    def setUp(self):
        self.engine = EslPhonicsEngine()
    def test_tier_1_reviewed_word_bank_matches(self):
        for w, exp in {'resignation': ['res', 'ig', 'na', 'tion'], 'beautiful': ['beau', 'ti', 'ful']}.items():
            self.assertEqual(self.engine.split_syllables(w), exp)
    def test_tier_2_idempotent_compound_deflection(self):
        self.assertEqual(self.engine.split_syllables('signpost'), ['sign', 'post'])
    def test_initial_silent_academic_clusters(self):
        self.assertEqual(self.engine.split_syllables('pneumatic'), ['pneu', 'mat', 'ic'])
    def test_medial_split_academic_clusters(self):
        self.assertEqual(self.engine.split_syllables('signature'), ['sig', 'na', 'ture'])

if __name__ == '__main__':
    unittest.main()'''
}

for path, content in files.items():
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Generated: {path}')
"
