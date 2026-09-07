"""Validated Merriam-Webster Collegiate/Learner API access."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.analysis.tracing import trace_event


logger = logging.getLogger(__name__)
_WORD_RE = re.compile(r"[^a-zA-Z'-]+")
_HEADWORD_MARKS_RE = re.compile(r"[*·‧•]")
_PRONUNCIATION_SEPARATOR_RE = re.compile(r"[-‐‑‒–—]")
_MAX_RESPONSE_BYTES = 1_048_576


@dataclass(frozen=True)
class MerriamWebsterResult:
    """A spelling-preserving, validated provider result."""

    word: str
    syllables: tuple[str, ...]
    pronunciation: str | None
    stress_index: int | None
    source: str = "merriam-webster"


Transport = Callable[[str, float], Any]


class MerriamWebsterProvider:
    """Fetch and validate one MW dictionary entry without breaking local analysis."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://www.dictionaryapi.com/api/v3/references/collegiate/json",
        timeout_seconds: float = 3.0,
        transport: Transport | None = None,
    ):
        self.api_key = (api_key or "").strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self._transport = transport or self._request_json
        self._cache: dict[str, MerriamWebsterResult | None] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def lookup(self, word: str) -> MerriamWebsterResult | None:
        """Return a validated result, or None for any unavailable/unsafe response."""
        normalized = _normalize_word(word)
        if normalized in self._cache:
            trace_event("MW-01", "provider_cache", normalized, "hit")
            return self._cache[normalized]
        if not self.enabled:
            trace_event("MW-01", "provider_guard", normalized, "disabled", skip=True)
            self._cache[normalized] = None
            return None

        trace_event("MW-01", "provider_lookup", normalized, "started")
        try:
            payload = self._transport(normalized, self.timeout_seconds)
        except Exception as error:  # pylint: disable=broad-exception-caught
            logger.warning(
                "merriam_webster_unavailable word=%r reason=%s",
                normalized,
                type(error).__name__,
            )
            trace_event(
                "MW-02",
                "provider_failure",
                normalized,
                {"reason": type(error).__name__},
                resolution="fallback",
            )
            self._cache[normalized] = None
            return None
        result, reason = self._parse_payload(normalized, payload)
        if result is None:
            logger.info("merriam_webster_rejected word=%r reason=%s", normalized, reason)
            trace_event(
                "MW-03",
                "provider_validation",
                normalized,
                {"accepted": False, "reason": reason},
                resolution="fallback",
            )
        else:
            trace_event("MW-03", "provider_validation", normalized, {"accepted": True, "syllables": result.syllables})
        self._cache[normalized] = result
        return result

    def _request_json(self, word: str, timeout: float) -> Any:
        url = f"{self.base_url}/{quote(word, safe='') }?key={quote(self.api_key, safe='')}"
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "syllabicator-v2"})
        with urlopen(request, timeout=timeout) as response:  # nosec B310: URL is configured explicitly.
            body = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise ValueError("response_too_large")
        return json.loads(body.decode("utf-8"))

    @classmethod
    def _parse_payload(cls, word: str, payload: Any) -> tuple[MerriamWebsterResult | None, str]:
        if not isinstance(payload, list):
            return None, "payload_not_list"
        for entry in payload:
            parsed = cls._parse_entry(word, entry)
            if parsed is not None:
                return parsed, "accepted"
        return None, "no_valid_matching_entry"

    @classmethod
    def _parse_entry(cls, word: str, entry: Any) -> MerriamWebsterResult | None:
        if not isinstance(entry, dict):
            return None
        meta = entry.get("meta")
        hwi = entry.get("hwi")
        if not isinstance(meta, dict) or not isinstance(hwi, dict):
            return None
        identifiers = [meta.get("id"), hwi.get("hw")]
        if not any(_same_word(word, value) for value in identifiers if isinstance(value, str)):
            return None
        raw_headword = hwi.get("hw")
        if not isinstance(raw_headword, str):
            return None
        syllables = _parse_headword(word, raw_headword)
        if syllables is None:
            return None
        pronunciation = _pronunciation(hwi.get("prs"))
        return MerriamWebsterResult(
            word=word,
            syllables=tuple(syllables),
            pronunciation=pronunciation,
            stress_index=_stress_index(pronunciation),
        )


def _normalize_word(value: str) -> str:
    return _WORD_RE.sub("", str(value)).strip().lower()


def _same_word(word: str, value: str) -> bool:
    candidate = _normalize_word(value.split(":", 1)[0].replace("*", ""))
    return candidate == word


def _parse_headword(word: str, raw_headword: str) -> list[str] | None:
    normalized = _HEADWORD_MARKS_RE.sub("-", raw_headword.lower())
    parts = [part.strip(" ?") for part in normalized.split("-") if part.strip(" ?")]
    if len(parts) < 1 or any(not re.fullmatch(r"[a-zA-Z']+", part) for part in parts):
        return None
    if "".join(parts).replace("'", "") != word.replace("'", ""):
        return None
    return parts


def _pronunciation(raw_prs: Any) -> str | None:
    if not isinstance(raw_prs, list):
        return None
    for item in raw_prs:
        if isinstance(item, dict) and isinstance(item.get("mw"), str) and item["mw"].strip():
            return item["mw"].strip()
    return None


def _stress_index(pronunciation: str | None) -> int | None:
    if not pronunciation:
        return None
    parts = [part for part in _PRONUNCIATION_SEPARATOR_RE.split(pronunciation) if part]
    for index, part in enumerate(parts):
        if "ˈ" in part or "'" in part:
            return index
    return None


__all__ = ["MerriamWebsterProvider", "MerriamWebsterResult"]
