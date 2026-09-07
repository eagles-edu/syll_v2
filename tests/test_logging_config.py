import logging

from app.analysis.tracing import (
    begin_analysis_trace,
    end_analysis_trace,
    set_trace_result,
    trace_event,
)
from app.logging_config import MarkdownTraceHandler


def test_markdown_trace_handler_renders_live_events(tmp_path):
    log_path = tmp_path / "DYNAMICALLY-log.md"
    logger = logging.getLogger("app.analysis.tracing")
    handler = MarkdownTraceHandler(log_path)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    token = begin_analysis_trace("resignation")
    try:
        trace_event("AFF-06", "affix_reduction_decision", "signa", "no_further_reduction")
        trace_event("REC-08", "reconciliation_decision", {"repeat": False}, {"result": []})
        trace_event(
            "CMP-01",
            "compound_detected",
            "signpost",
            ["sign", "post"],
            branch="substring_split_loop",
        )
        set_trace_result({"formatted": "res-ig-ná-tion"})
    finally:
        end_analysis_trace(token)
        logger.removeHandler(handler)
        handler.close()

    rendered = log_path.read_text(encoding="utf-8")
    assert "# Dynamic Analysis Trace" in rendered
    assert "## " in rendered and "— `resignation`" in rendered
    assert "### Step 000 — API-00 / `input_word`" in rendered
    assert "### Step 001 — AFF-06 / `affix_reduction_decision`" in rendered
    assert "- Decision: `NFRP`" in rendered
    assert "- Resolution: `complete`" in rendered
    assert "- Repetition: `false`" in rendered
    assert "- Branch: `substring_split_loop`" in rendered
    assert "### Completed — `resignation`" in rendered
    assert '"formatted": "res-ig-ná-tion"' in rendered
