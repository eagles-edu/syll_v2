import logging

from flask import Blueprint, jsonify, request

from app.services.word_service import WordAnalysisService

bp = Blueprint("api", __name__, url_prefix="/api")
service = WordAnalysisService()
logger = logging.getLogger(__name__)


def _request_service() -> WordAnalysisService:
    """Return the shared service or an explicitly bypassed v2 service."""
    bypass_requested = request.args.get("bypass", "false").lower() == "true"
    if bypass_requested:
        return WordAnalysisService(use_word_bank=True, bypass_cache=True)
    return service


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


def _coerce_bulk_input():
    if request.is_json:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            if "word" in payload and "words" not in payload and "text" not in payload:
                return payload["word"]
            if "words" in payload or "text" in payload or "input" in payload:
                return payload.get("words") or payload.get("text") or payload.get("input")
        if isinstance(payload, list):
            return payload
        if payload is not None:
            return payload

    if request.form:
        for key in ("words", "text", "input", "word"):
            if key in request.form and request.form.get(key):
                return request.form.get(key)

    raw = request.get_data(cache=True, as_text=True)
    if raw and raw.strip():
        return raw
    return None


def _json_result(raw, analysis_service: WordAnalysisService | None = None):
    """Analyze one request payload and translate domain errors to HTTP."""
    active_service = analysis_service or service
    try:
        if isinstance(raw, str) and not _is_bulk_text(raw):
            return jsonify(active_service.analyze(raw))
        results = active_service.analyze_batch(raw)
        return jsonify({
            "count": len(results),
            "results": results,
            "items": results,
            "cache_bypassed": bool(getattr(active_service, "bypass_cache", False)),
        })
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception:  # pragma: no cover - defensive HTTP boundary
        logger.exception("Unexpected word-analysis failure")
        return jsonify({"error": "Unable to analyze the supplied word input."}), 500


def _is_bulk_text(raw: str) -> bool:
    return bool(
        any(delimiter in raw for delimiter in ("\n", ",", ";", "\t"))
        or len(raw.strip().split()) > 1
        or raw.strip().startswith("[")
    )


@bp.get("/analyze")
def analyze_words_query():
    values = request.args.getlist("words")
    raw = values if len(values) > 1 else (
        values[0] if values else request.args.get("text") or request.args.get("input") or request.args.get("word")
    )
    if raw is None:
        return jsonify({"error": "Word input is required."}), 400
    return _json_result(raw, _request_service())


@bp.post("/analyze")
def analyze_words_post():
    raw = _coerce_bulk_input()
    if raw is None:
        return jsonify({"error": "Word input is required."}), 400
    return _json_result(raw, _request_service())


@bp.post("/analyze/bulk")
@bp.post("/bulk-analyze")
def analyze_bulk_words():
    return analyze_words_post()


@bp.get("/analyze/<word>")
def analyze_word(word):
    return _json_result(word, _request_service())


__all__ = ["bp"]
