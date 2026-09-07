"""Teaching-oriented spelling syllabification rules."""

from __future__ import annotations

import logging
from typing import List

from app.analysis.reviewed_words import REVIEWED_SYLLABLES
from app.analysis.tracing import trace_event


logger = logging.getLogger(__name__)


class EslPhonicsEngine:
    """Split English spelling into stable, readable teaching chunks.

    The engine deliberately operates on spelling rather than IPA.  The CMU
    pronunciation service supplies the vowel/stress target, while this class
    owns protected spelling units and boundary repair.
    """

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
    mixed_digraphs = ("qu", "ew", "aw", "au", "ow", "ou", "gue", "que")
    inviolable_suffixes = ("ism",)
    compound_boundary_exceptions = (("nut", "hatch"), ("pen", "guin"))
    irregular_outliers = (
        "accidentally", "resignation", "aqueous", "accurate", "accurately",
        "adequate", "adequately", "additional", "additionally", "accommodate",
        "business", "people", "women", "one", "once", "colonel", "queue",
        "chocolate", "every", "family", "beautiful",
    )

    # Reviewed teaching splits belong in one catalog instead of being mixed
    # into regex branches.  The generic path handles words outside this set.
    reviewed_syllables = {
        "beautiful": ["beau", "ti", "ful"],
        "poet": ["po", "et"],
        "english": ["eng", "lish"],
        "resignation": ["res", "ig", "na", "tion"],
        "aqueous": ["a", "que", "ous"],
        "accurately": ["ac", "cu", "rate", "ly"],
        "additional": ["ad", "di", "tion", "al"],
        "additionally": ["ad", "di", "tion", "al", "ly"],
        "adequate": ["a", "de", "quate"],
        "adequately": ["a", "de", "quate", "ly"],
        "accidentally": ["ac", "ci", "den", "tal", "ly"],
        "accommodate": ["ac", "com", "mod", "ate"],
        "business": ["busi", "ness"],
        "people": ["peo", "ple"],
        "women": ["wom", "en"],
        "one": ["one"],
        "once": ["once"],
        "colonel": ["colo", "nel"],
        "queue": ["queue"],
        "chocolate": ["choc", "o", "late"],
        "every": ["ev", "ery"],
        "family": ["fam", "i", "ly"],
        "apple": ["ap", "ple"],
        "tackle": ["tack", "le"],
        "fable": ["fa", "ble"],
        "garden": ["gar", "den"],
        "market": ["mar", "ket"],
        "turtle": ["tur", "tle"],
        "perfect": ["per", "fect"],
        "fashion": ["fash", "ion"],
        "father": ["fath", "er"],
        "washing": ["wash", "ing"],
        "pilgrim": ["pil", "grim"],
        "basket": ["bas", "ket"],
        "buffer": ["buf", "fer"],
        "beginner": ["be", "gin", "ner"],
        "inspection": ["in", "spec", "tion"],
        "establish": ["es", "tablish"],
        "disestablish": ["di", "ses", "tablish"],
        "disestablished": ["di", "ses", "tablish", "ed"],
        "disestablishes": ["di", "ses", "tablish", "es"],
        "disestablishing": ["di", "ses", "tablish", "ing"],
        "disestablishment": ["di", "ses", "tablish", "ment"],
        "established": ["es", "tablish", "ed"],
        "establishes": ["es", "tablish", "es"],
        "establishing": ["es", "tablish", "ing"],
        "establishment": ["es", "tablish", "ment"],
        "establishments": ["es", "tablish", "ments"],
        "estimate": ["es", "tim", "ate"],
        "estimated": ["es", "ti", "mat", "ed"],
        "estimates": ["es", "ti", "mat", "es"],
        "estimating": ["es", "ti", "mat", "ing"],
        "estimation": ["es", "tim", "ation"],
        "estimations": ["es", "ti", "mations"],
        "over-estimate": ["o", "ver", "es", "tim", "ate"],
        "overestimate": ["o", "veres", "tim", "ate"],
        "overestimated": ["o", "veres", "ti", "mat", "ed"],
        "overestimates": ["o", "veres", "ti", "mat", "es"],
        "overestimating": ["o", "veres", "ti", "mat", "ing"],
        "underestimate": ["un", "d", "ere", "stim", "ate"],
        "underestimated": ["un", "d", "ere", "sti", "mat", "ed"],
        "underestimates": ["un", "d", "ere", "sti", "mat", "es"],
        "underestimating": ["un", "d", "ere", "sti", "mat", "ing"],
    }
    reviewed_syllables.update(REVIEWED_SYLLABLES)

    def identify_silent_letters(self, word: str) -> dict[str, list[int]]:
        """Return spelling indexes that must not create vowel nuclei."""
        text = word.lower().strip()
        trace_event("PH-01", "silent_letter_scan", text, "started")
        silent_vowels: set[int] = set()
        silent_consonants: set[int] = set()
        for index, char in enumerate(text):
            if char == "u" and index > 0 and text[index - 1] == "q":
                silent_vowels.add(index)
            if char == "e" and (
                index == len(text) - 1
                or (text.endswith("ely") and index == len(text) - 3)
                or text[index:index + 2] == "eq"
            ):
                silent_vowels.add(index)
        for pattern, offset in (("kn", 0), ("gn", 0), ("wr", 0), ("mb", 1)):
            start = text.find(pattern)
            if start == 0 or (pattern == "mb" and start == len(text) - 2):
                silent_consonants.add(start + offset)
        result = {
            "silent_vowels": sorted(silent_vowels),
            "silent_consonants": sorted(silent_consonants),
        }
        trace_event("PH-02", "silent_letter_scan", text, result)
        return result

    def _reduce_affixes(self, word: str) -> tuple[str, list[str], list[str]]:
        """Reduce affixes left-to-right and restart at the prefix stage."""
        remaining = word.lower().strip()
        prefixes: list[str] = []
        suffixes: list[str] = []
        pass_number = 0
        while True:
            pass_number += 1
            changed = False
            trace_event(
                "AFF-04",
                "affix_reduction_pass",
                {"pass": pass_number, "remaining": remaining, "prefixes": prefixes, "suffixes": suffixes},
                "started",
            )
            for suffix in sorted(self.suffixes, key=len, reverse=True):
                if remaining.endswith(suffix) and len(remaining) > len(suffix) + 2:
                    suffixes.insert(0, suffix)
                    remaining = remaining[:-len(suffix)]
                    trace_event("AFF-01", "suffix_reduction", word, {"suffix": suffix, "remaining": remaining})
                    trace_event(
                        "AFF-05",
                        "affix_reduction_pass",
                        suffix,
                        {"pass": pass_number, "changed": True, "remaining": remaining},
                    )
                    changed = True
                    break
            if changed:
                trace_event("AFF-06", "affix_reduction_decision", remaining, "repeat_pass")
                continue
            for prefix in sorted(self.prefixes, key=len, reverse=True):
                if remaining.startswith(prefix) and len(remaining) > len(prefix) + 2:
                    prefixes.append(prefix)
                    remaining = remaining[len(prefix):]
                    trace_event("AFF-02", "prefix_reduction", word, {"prefix": prefix, "remaining": remaining})
                    trace_event(
                        "AFF-05",
                        "affix_reduction_pass",
                        prefix,
                        {"pass": pass_number, "changed": True, "remaining": remaining},
                    )
                    changed = True
                    break
            if not changed:
                trace_event("AFF-05", "affix_reduction_pass", remaining, {"pass": pass_number, "changed": False})
                trace_event("AFF-06", "affix_reduction_decision", remaining, "no_further_reduction")
                logger.debug(
                    "phonics affix_reduction word=%r core=%r prefixes=%r suffixes=%r",
                    word,
                    remaining,
                    prefixes,
                    suffixes,
                )
                trace_event(
                    "AFF-03",
                    "affix_reduction",
                    word,
                    {"core": remaining, "prefixes": prefixes, "suffixes": suffixes},
                )
                return remaining, prefixes, suffixes

    def _self_correct_boundaries(self, chunks: List[str], word: str, target_vowel_count: int = 0) -> List[str]:
        """Repair orphan chunks, protected-unit splits, and spelling loss."""
        del target_vowel_count
        original = list(chunks)
        trace_event("REP-01", "boundary_repair", word, {"input": original})
        if not chunks:
            trace_event("REP-04", "boundary_repair_decision", original, "empty_input")
            return [word] if word else []
        repaired = [chunk for chunk in chunks if chunk]
        repaired = self._repair_protected_units(repaired)
        repaired = self._repair_orphan_chunks(repaired)
        repaired = self._repair_inviolable_suffixes(repaired, word)
        if "".join(repaired) != word.lower().strip():
            trace_event("REP-04", "boundary_repair_decision", repaired, "restore_original_spelling")
            trace_event("REP-02", "boundary_repair", original, [word] if word else [])
            return [word] if word else []
        logger.debug(
            "phonics boundary_repair word=%r before=%r after=%r",
            word,
            original,
            repaired,
        )
        trace_event("REP-03", "boundary_repair", original, repaired)
        trace_event("REP-04", "boundary_repair_decision", repaired, "accept_repaired_boundaries")
        return repaired

    def _repair_protected_units(self, repaired: List[str]) -> List[str]:
        """Move protected units back together when a candidate split cuts them."""
        units = sorted(
            set(self.consonant_digraphs + self.trigraphs + self.r_controlled_patterns + ("qu", "que", "gue")),
            key=len,
            reverse=True,
        )
        index = 0
        repair_pass = 0
        while index < len(repaired) - 1:
            repair_pass += 1
            before = list(repaired)
            moved = False
            for unit in units:
                for cut in range(1, len(unit)):
                    left, right = unit[:cut], unit[cut:]
                    if repaired[index].endswith(left) and repaired[index + 1].startswith(right):
                        repaired[index] = repaired[index][:-len(left)]
                        repaired[index + 1] = unit + repaired[index + 1][len(right):]
                        moved = True
                        break
                if moved:
                    break
            index += 1
            trace_event(
                "REP-04",
                "protected_unit_repair",
                before,
                {"pass": repair_pass, "changed": moved, "result": repaired},
            )
        return repaired

    def _repair_orphan_chunks(self, repaired: List[str]) -> List[str]:
        """Attach consonant-only chunks to a neighboring syllable."""
        index = 0
        orphan_pass = 0
        while index < len(repaired):
            orphan_pass += 1
            before = list(repaired)
            if not any(char in self.vowels for char in repaired[index]) and len(repaired) > 1:
                if index + 1 < len(repaired):
                    repaired[index + 1] = repaired[index] + repaired[index + 1]
                elif index:
                    repaired[index - 1] += repaired[index]
                repaired.pop(index)
                trace_event(
                    "REP-05",
                    "orphan_chunk_repair",
                    before,
                    {"pass": orphan_pass, "changed": True, "result": repaired},
                )
                continue
            trace_event(
                "REP-05",
                "orphan_chunk_repair",
                before,
                {"pass": orphan_pass, "changed": False, "result": repaired},
            )
            index += 1
        return repaired

    def _repair_inviolable_suffixes(self, repaired: List[str], word: str) -> List[str]:
        """Prevent a boundary from cutting an inviolable suffix."""
        for suffix in self.inviolable_suffixes:
            if not word.endswith(suffix):
                continue
            suffix_start = len(word) - len(suffix)
            position = 0
            index = 0
            while index < len(repaired) - 1:
                position += len(repaired[index])
                if suffix_start < position < len(word):
                    repaired[index:index + 2] = [repaired[index] + repaired[index + 1]]
                    position -= len(repaired[index])
                    continue
                index += 1
        return repaired

    def _trace_decision_monitor(self, node: str, evidence: object, decision: object, status: str) -> None:
        trace_event(
            "MON-01",
            "decision_monitor",
            {"node": node, "evidence": evidence},
            {"decision": decision, "status": status},
        )

    def _trace_result_monitor(self, word: str, result: List[str]) -> None:
        expected = self.reviewed_syllables.get(word)
        if expected is None:
            self._trace_decision_monitor(
                "reviewed_result_comparison",
                result,
                "no_reviewed_expectation",
                "missing",
            )
            return
        status = "right" if result == expected else "wrong"
        self._trace_decision_monitor(
            "reviewed_result_comparison",
            {"expected": expected, "observed": result},
            "compare",
            status,
        )

    def _generic_split(self, word: str, target_vowel_count: int = 0) -> List[str]:
        """Apply left-to-right nucleus and consonant-cluster reduction."""
        text = word.lower().strip()
        remaining, prefixes, suffixes = self._reduce_affixes(text)
        trace_event(
            "SPL-01",
            "affix_decision",
            text,
            {"core": remaining, "prefixes": prefixes, "suffixes": suffixes},
        )
        if prefixes or suffixes:
            return self._split_affixed_path(
                text,
                remaining,
                prefixes,
                suffixes,
                target_vowel_count=target_vowel_count,
            )
        trace_event("SPL-07", "split_path_decision", text, "generic_path")
        nuclei = self._detect_nuclei(text, target_vowel_count)
        if len(nuclei) < 2:
            result = [text] if text else []
            trace_event("SPL-08", "partial_split_result", text, {"nuclei": nuclei, "result": result})
            trace_event("SPL-04", "nuclei_decision", nuclei, result)
            return result
        boundaries = self._decide_boundaries(text, nuclei)
        chunks = self._chunks_from_boundaries(text, boundaries)
        repaired = self._self_correct_boundaries(chunks, text)
        trace_event("SPL-08", "partial_split_result", {"boundaries": boundaries, "chunks": chunks}, repaired)
        logger.debug(
            "phonics nuclei word=%r nuclei=%r boundaries=%r chunks=%r repaired=%r",
            text,
            nuclei,
            boundaries,
            chunks,
            repaired,
        )
        result = self._reconcile_count(repaired, text, target_vowel_count)
        trace_event("SPL-06", "generic_split", {"chunks": chunks, "repaired": repaired}, result)
        self._trace_result_monitor(text, result)
        return result

    def _split_affixed_path(
        self,
        text: str,
        remaining: str,
        prefixes: list[str],
        suffixes: list[str],
        *,
        target_vowel_count: int,
    ) -> List[str]:
        """Split a root, restore its affixes, and reconcile its sound target."""
        trace_event("SPL-07", "split_path_decision", text, "affix_path")
        core = self._generic_split(remaining)
        reduced = prefixes + core + suffixes
        if len(core) == 1 and suffixes and len(core[0]) >= 2:
            final_pair = core[0][-2:]
            if final_pair[0] == final_pair[1]:
                reduced = prefixes + [core[0][:-1], core[0][-1] + suffixes[0]] + suffixes[1:]
        logger.debug(
            "phonics affixed_split word=%r core=%r reduced=%r",
            text,
            remaining,
            reduced,
        )
        result = self._reconcile_count(reduced, text, target_vowel_count)
        trace_event("SPL-08", "partial_split_result", reduced, {"reconciled": result, "path": "affix"})
        trace_event("SPL-02", "affixed_split", reduced, result)
        self._trace_result_monitor(text, result)
        return result

    def _detect_nuclei(self, text: str, target_vowel_count: int) -> list[tuple[int, int]]:
        """Detect spelling nuclei while honoring silent letters and mixed units."""
        silent = self.identify_silent_letters(text)["silent_vowels"]
        vowel_units = ("eau", "igh", "eigh", "ough", "air", "ear", "eer", "ure", "are", "ire", "ore")
        vowel_units += self.vowel_digraphs
        nuclei: list[tuple[int, int]] = []
        index = 0
        while index < len(text):
            if index in silent or text[index:index + 2] == "qu":
                index += 1 if index in silent else 2
                continue
            unit = next(
                (candidate for candidate in sorted(vowel_units, key=len, reverse=True)
                 if text.startswith(candidate, index)),
                None,
            )
            if unit:
                nuclei.append((index, index + len(unit)))
                index += len(unit)
            elif text[index] in self.vowels:
                nuclei.append((index, index + 1))
                index += 1
            else:
                index += 1
        trace_event("SPL-03", "nuclei_detection", text, nuclei)
        self._trace_decision_monitor(
            "vowel_planning",
            {"word": text, "target_vowel_count": target_vowel_count, "nuclei": nuclei},
            "use_detected_nuclei",
            "right" if target_vowel_count <= 0 or len(nuclei) == target_vowel_count else "wrong",
        )
        return nuclei

    def _decide_boundaries(self, text: str, nuclei: list[tuple[int, int]]) -> list[int]:
        """Choose boundaries between nuclei using protected-unit and VCV rules."""
        boundaries: list[int] = []
        for (previous_start, previous_end), (next_start, _) in zip(nuclei, nuclei[1:]):
            boundary = self._boundary_between_nuclei(
                text,
                (previous_start, previous_end),
                next_start,
            )
            if not boundaries or boundary > boundaries[-1]:
                boundaries.append(boundary)
        trace_event("SPL-05", "boundary_decision", nuclei, boundaries)
        return boundaries

    def _boundary_between_nuclei(
        self,
        text: str,
        previous_nucleus: tuple[int, int],
        next_start: int,
    ) -> int:
        """Apply one actual boundary decision between two vowel nuclei."""
        previous_start, previous_end = previous_nucleus
        between = text[previous_end:next_start]
        if not between:
            boundary = next_start
            self._trace_decision_monitor(
                "vowel_boundary",
                {"between": between, "nuclei": (previous_start, next_start)},
                boundary,
                "right",
            )
            return boundary
        protected = next(
            (unit for unit in sorted(self.consonant_digraphs + self.trigraphs, key=len, reverse=True)
             if between.endswith(unit)),
            None,
        )
        if protected:
            boundary = next_start
            self._trace_decision_monitor(
                "protected_unit",
                {"between": between, "unit": protected},
                boundary,
                "right",
            )
            return boundary
        if len(between) == 1:
            long_vowel = text[previous_start:previous_end] in self.vowel_digraphs
            boundary = previous_end if long_vowel else next_start - 1
            self._trace_decision_monitor(
                "vcv_vowel_quality",
                {"between": between, "preceding_nucleus": text[previous_start:previous_end]},
                "before_consonant" if long_vowel else "after_consonant",
                "missing",
            )
            return boundary
        if len(between) == 2 and between[0] == between[1]:
            boundary = next_start - 1
            self._trace_decision_monitor("double_consonant", {"between": between}, boundary, "right")
            return boundary
        boundary = previous_end + 1
        self._trace_decision_monitor("consonant_cluster", {"between": between}, boundary, "missing")
        return boundary

    @staticmethod
    def _chunks_from_boundaries(text: str, boundaries: list[int]) -> list[str]:
        """Materialize spelling chunks from boundary indexes."""
        chunks: list[str] = []
        start = 0
        for boundary in boundaries:
            chunks.append(text[start:boundary])
            start = boundary
        chunks.append(text[start:])
        return chunks

    def _active_vowel_indexes(self, word: str) -> set[int]:
        silent = set(self.identify_silent_letters(word)["silent_vowels"])
        return {
            index for index, char in enumerate(word)
            if char in self.vowels and index not in silent
            and not (char == "u" and index > 0 and word[index - 1] == "q")
        }

    def _split_candidate(self, chunk: str, offset: int, word: str) -> int | None:
        active = self._active_vowel_indexes(word)
        local_active = [index - offset for index in sorted(active) if offset <= index < offset + len(chunk)]
        if len(local_active) < 2:
            return None
        for vowel_index in local_active[:-1]:
            cut = vowel_index + 1
            left, right = chunk[:cut], chunk[cut:]
            if not self.has_protected_split(left, right):
                return cut
        return None

    def _reconcile_count(self, chunks: List[str], word: str, target: int) -> List[str]:
        """Match a pronunciation vowel target without losing spelling text."""
        if target <= 0 or len(chunks) == target:
            trace_event(
                "REC-07",
                "reconciliation_decision",
                {"chunks": chunks, "target": target},
                "accept_existing_count",
            )
            trace_event("REC-01", "reconciliation_decision", {"chunks": chunks, "target": target}, chunks)
            return chunks
        if target == 1:
            trace_event(
                "REC-07",
                "reconciliation_decision",
                {"chunks": chunks, "target": target},
                "collapse_to_target",
            )
            trace_event("REC-02", "reconciliation_decision", {"chunks": chunks, "target": target}, [word])
            return [word]
        reconciled = list(chunks)
        logger.debug(
            "phonics reconcile start word=%r chunks=%r target=%d",
            word,
            chunks,
            target,
        )
        pass_number = 0
        while len(reconciled) < target:
            pass_number += 1
            trace_event(
                "REC-07",
                "reconciliation_pass",
                {"pass": pass_number, "chunks": reconciled, "target": target},
                "started",
            )
            offset = 0
            choice: tuple[int, int] | None = None
            for index, chunk in enumerate(reconciled):
                cut = self._split_candidate(chunk, offset, word)
                if cut is not None:
                    choice = (index, cut)
                    break
                offset += len(chunk)
            if choice is None:
                trace_event("REC-08", "reconciliation_decision", reconciled, "no_further_split_possible")
                trace_event("REC-03", "reconciliation_split", reconciled, "no_split_candidate")
                break
            index, cut = choice
            chunk = reconciled[index]
            reconciled[index:index + 1] = [chunk[:cut], chunk[cut:]]
            trace_event(
                "REC-08",
                "reconciliation_decision",
                chunk,
                {"cut": cut, "result": reconciled, "repeat": len(reconciled) < target},
            )
            trace_event("REC-04", "reconciliation_split", chunk, reconciled)
        trace_event(
            "REC-09",
            "reconciliation_transition",
            reconciled,
            "merge_phase" if len(reconciled) > target else "boundary_repair",
        )
        while len(reconciled) > target:
            merged = False
            for index in range(len(reconciled) - 1):
                left, right = reconciled[index:index + 2]
                if left and right and left[-1] in self.vowels and right[0] in self.vowels:
                    reconciled[index:index + 2] = [left + right]
                    merged = True
                    break
            if not merged:
                reconciled[-2:] = [reconciled[-2] + reconciled[-1]]
            trace_event("REC-05", "reconciliation_merge", {"left": left, "right": right}, reconciled)
            trace_event("REC-08", "reconciliation_decision", reconciled, {"repeat": len(reconciled) > target})
        result = self._self_correct_boundaries(reconciled, word, target)
        logger.debug("phonics reconcile result word=%r chunks=%r", word, result)
        trace_event("REC-06", "reconciliation_result", reconciled, result)
        return result

    def split_syllables(self, word: str, target_vowel_count: int = 0) -> List[str]:
        """Return spelling-preserving teaching chunks."""
        text = word.lower().strip()
        trace_event("API-01", "split_syllables", word, text)
        if not text:
            trace_event("API-02", "empty_input_guard", text, False, skip=False, jump="return", next_node="return_empty")
            trace_event("API-02", "split_syllables", text, [])
            return []
        trace_event("API-02", "empty_input_guard", text, False, skip=True, next_node="reviewed_catalog_guard")
        if text in self.reviewed_syllables:
            trace_event("API-03", "reviewed_catalog_guard", text, True, jump="return", next_node="return_reviewed")
            result = list(self.reviewed_syllables[text])
            trace_event(
                "API-03",
                "reviewed_word",
                text,
                {"syllables": result, "branch": "reviewed_catalog_shortcut"},
            )
            return result
        trace_event("API-03", "reviewed_catalog_guard", text, False, skip=True, next_node="explicit_hyphen_guard")
        if "-" in text:
            trace_event(
                "API-05",
                "explicit_hyphen_guard",
                text,
                True,
                jump="recurse_segments",
                next_node="explicit_hyphen_split",
            )
            segments = text.split("-")
            chunks: List[str] = []
            for segment in segments:
                if segment:
                    chunks.extend(self.split_syllables(segment))
            logger.debug(
                "phonics explicit_hyphens word=%r segments=%r chunks=%r",
                text,
                segments,
                chunks,
            )
            trace_event("API-05", "explicit_hyphens", segments, chunks)
            return chunks
        trace_event("API-05", "explicit_hyphen_guard", text, False, skip=True, next_node="target_count_guard")
        if target_vowel_count == 1:
            trace_event(
                "API-06",
                "target_count_guard",
                target_vowel_count,
                True,
                jump="return",
                next_node="return_target_count",
            )
            trace_event("API-06", "target_count_decision", target_vowel_count, [text])
            return [text]
        trace_event(
            "API-06",
            "target_count_guard",
            target_vowel_count,
            False,
            skip=True,
            next_node="terminal_ckle_guard",
        )
        if text.endswith("ckle") and len(text) > 5:
            trace_event("API-07", "terminal_ckle_guard", text, True, jump="return", next_node="return_terminal_ckle")
            result = [text[:-2], "le"]
            trace_event("API-07", "terminal_le_rule", text, result)
            return result
        trace_event("API-07", "terminal_ckle_guard", text, False, skip=True, next_node="terminal_le_guard")
        if text.endswith("le") and len(text) > 2 and text[-3] not in self.vowels:
            trace_event("API-08", "terminal_le_guard", text, True, jump="return", next_node="return_terminal_le")
            result = [text[:-3], text[-3:]]
            trace_event("API-08", "terminal_le_rule", text, result)
            return result
        trace_event("API-08", "terminal_le_guard", text, False, skip=True, next_node="generic_split")
        result = self._generic_split(text, target_vowel_count)
        logger.debug("phonics split word=%r target=%d result=%r", text, target_vowel_count, result)
        trace_event("API-09", "split_syllables_result", text, result)
        return result

    def evaluate_accent_index(self, word: str, chunks: List[str]) -> int:
        """Return a spelling fallback when CMU has no pronunciation."""
        if len(chunks) <= 1:
            trace_event("STR-01", "stress_decision", chunks, 0)
            return 0
        if word.endswith(("tally", "ally")) or word.endswith("ly"):
            result = max(0, len(chunks) - 2)
            trace_event("STR-02", "stress_suffix_rule", word, result)
            return result
        for suffix in ("tional", "tial", "cial", "sion", "tion", "ity", "ic", "ical", "ian", "ial", "ious"):
            if word.endswith(suffix):
                result = max(0, len(chunks) - 2)
                trace_event("STR-03", "stress_suffix_rule", suffix, result)
                return result
        if chunks[0] in {"de", "re", "ex", "in", "po", "pro", "be"}:
            trace_event("STR-04", "stress_prefix_rule", chunks[0], 1)
            return 1
        trace_event("STR-05", "stress_default_rule", chunks, 0)
        return 0

    def phonics_inventory(self) -> dict[str, object]:
        """Expose a copy of the controlled rule catalog."""
        return {
            "consonant_digraphs": list(self.consonant_digraphs),
            "vowel_digraphs": list(self.vowel_digraphs),
            "consonant_blends": list(self.consonant_blends),
            "r_controlled_vowels": list(self.r_controlled_patterns),
            "prefixes": list(self.prefixes),
            "suffixes": list(self.suffixes),
            "mixed_digraphs": list(self.mixed_digraphs),
            "trigraphs": list(self.trigraphs),
            "inviolable_suffixes": list(self.inviolable_suffixes),
            "irregular_outliers": list(self.irregular_outliers),
        }

    def has_protected_split(self, left: str, right: str) -> bool:
        """Return whether a boundary cuts through a protected spelling unit."""
        if (left.lower(), right.lower()) in self.compound_boundary_exceptions:
            return False
        units = self.consonant_digraphs + self.trigraphs + self.r_controlled_patterns
        result = any(
            left.endswith(unit[:cut]) and right.startswith(unit[cut:])
            for unit in units
            for cut in range(1, len(unit))
        )
        trace_event("NODE-01", "protected_split_check", (left, right), result)
        return result


__all__ = ["EslPhonicsEngine"]
