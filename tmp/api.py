# app/routes/api.py
from __future__ import annotations

import logging
from flask import Blueprint, jsonify, request
from app.services.word_service import WordAnalysisService
from app.config import settings

bp = Blueprint("api", __name__, url_prefix="/api")
logger = logging.getLogger(__name__)


@bp.route("/analyze", methods=["POST"])
def analyze():
    """Analyze incoming word structural vectors dynamically."""
    url_bypass = request.args.get("bypass", "false").lower() == "true"
    active_bypass = url_bypass or settings.debug

    service = WordAnalysisService(use_word_bank=True, bypass_cache=active_bypass)
    raw_data = request.get_json() or {}

    try:
        if "words" in raw_data:
            results = service.analyze_batch(raw_data["words"])
            return jsonify({"results": results, "cache_bypassed": active_bypass}), 200
        elif "word" in raw_data:
            # Reconcile backend input structures for string array parameters
            word_input = raw_data["word"]
            if isinstance(word_input, list) and len(word_input) > 0:
                word_input = word_input[0]
            result = service.analyze(str(word_input))
            return jsonify({"results": [result], "cache_bypassed": active_bypass}), 200
        else:
            return jsonify({"error": "Payload must include 'word' or 'words' keys."}), 400

    except Exception as e:
        logger.error("API route execution breakdown failure: %s", str(e))
        return jsonify({"error": str(e)}), 500
