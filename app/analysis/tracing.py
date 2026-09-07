"""Context-local runtime tracing for the real syllabication decision path."""

from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass, field
from typing import Any


logger = logging.getLogger(__name__)
_current_trace: contextvars.ContextVar["AnalysisTrace | None"] = contextvars.ContextVar(
    "analysis_trace",
    default=None,
)


@dataclass(frozen=True)
class TraceEvent:  # pylint: disable=too-many-instance-attributes
    """One event emitted at the point an analysis operation executes."""

    step: int
    rule: str
    node: str
    input_value: Any
    output_value: Any
    decision: Any = None
    resolution: str = "apply"
    branch: Any = None
    repetition: Any = None
    status: Any = None
    skip: Any = None
    jump: Any = None
    next_node: Any = None


@dataclass
class AnalysisTrace:
    """Record and immediately log every operation in one analysis invocation."""

    word: str
    events: list[TraceEvent] = field(default_factory=list)
    final_result: Any = None

    def emit(
        self,
        rule: str,
        node: str,
        input_value: Any,
        result: Any,
        *,
        resolution: str | None = None,
        branch: Any = None,
        skip: Any = None,
        jump: Any = None,
        next_node: Any = None,
    ) -> None:
        """Append and log one real event without reconstructing later steps."""
        event = TraceEvent(
            step=len(self.events),
            rule=rule,
            node=node,
            input_value=input_value,
            output_value=result,
            decision=_decision(node, result),
            resolution=resolution or _resolution(result, skip=skip, jump=jump),
            branch=branch if branch is not None else _branch(result),
            repetition=_repetition(input_value, result),
            status=_status(result),
            skip=skip,
            jump=jump,
            next_node=next_node,
        )
        self.events.append(event)
        logger.debug(
            "analysis_step step=%03d word=%r rule=%s node=%s input=%r output=%r "
            "decision=%r branch=%r repetition=%r status=%r skip=%r jump=%r next=%r",
            event.step,
            self.word,
            event.rule,
            event.node,
            event.input_value,
            event.output_value,
            event.decision,
            event.branch,
            event.repetition,
            event.status,
            event.skip,
            event.jump,
            event.next_node,
            extra={
                "analysis_trace_event": event,
                "analysis_trace_word": self.word,
            },
        )

    def set_result(self, result: Any) -> None:
        """Attach the public result to the already-emitted trace context."""
        self.final_result = result


def begin_analysis_trace(word: str) -> contextvars.Token:
    """Start a trace and emit the first normalization input event."""
    trace = AnalysisTrace(word)
    token = _current_trace.set(trace)
    trace.emit("API-00", "input_word", word, word)
    return token


def end_analysis_trace(token: contextvars.Token) -> None:
    """Emit invocation completion metadata and restore the prior context."""
    trace = _current_trace.get()
    if trace is not None:
        logger.debug(
            "analysis_trace_complete word=%r steps=%d result=%r",
            trace.word,
            len(trace.events),
            trace.final_result,
            extra={
                "analysis_trace_complete": {
                    "word": trace.word,
                    "steps": len(trace.events),
                    "result": trace.final_result,
                }
            },
        )
    _current_trace.reset(token)


def set_trace_result(result: Any) -> None:
    """Attach the public result before the invocation completion log."""
    trace = _current_trace.get()
    if trace is not None:
        trace.set_result(result)


def trace_event(
    rule: str,
    node: str,
    input_value: Any,
    result: Any,
    *,
    resolution: str | None = None,
    branch: Any = None,
    skip: Any = None,
    jump: Any = None,
    next_node: Any = None,
) -> None:
    """Emit an event to the active trace at the caller's execution point."""
    trace = _current_trace.get()
    if trace is not None:
        trace.emit(
            rule,
            node,
            input_value,
            result,
            resolution=resolution,
            branch=branch,
            skip=skip,
            jump=jump,
            next_node=next_node,
        )


def _decision(node: str, result: Any) -> Any:
    if result == "no_further_reduction":
        return "NFRP"
    if isinstance(result, dict):
        if "decision" in result:
            return result["decision"]
        if node.endswith("_decision"):
            return result
        return None
    if node.endswith("_decision") or node == "decision_monitor":
        return result
    return None


def _resolution(result: Any, *, skip: Any = None, jump: Any = None) -> str:
    """Classify the control-flow outcome of one emitted node."""
    if skip is True:
        return "skip"
    if jump is not None:
        return "jump"
    if result == "repeat_pass" or _branch(result) == "repeat_pass":
        return "repeat"
    if result == "no_further_reduction":
        return "complete"
    if _status(result) == "error":
        return "error"
    return "apply"


def _branch(result: Any) -> Any:
    if isinstance(result, dict):
        return result.get("branch") or result.get("path")
    if isinstance(result, str) and result in {
        "repeat_pass",
        "no_further_reduction",
        "merge_phase",
        "boundary_repair",
    }:
        return result
    return None


def _repetition(input_value: Any, result: Any) -> Any:
    if isinstance(input_value, dict):
        if "pass" in input_value:
            return input_value["pass"]
        if "repeat" in input_value:
            return input_value["repeat"]
    if isinstance(result, dict):
        if "pass" in result:
            return result["pass"]
        if "repeat" in result:
            return result["repeat"]
    if result == "repeat_pass":
        return True
    return None


def _status(result: Any) -> Any:
    return result.get("status") if isinstance(result, dict) else None


__all__ = [
    "AnalysisTrace",
    "TraceEvent",
    "begin_analysis_trace",
    "end_analysis_trace",
    "set_trace_result",
    "trace_event",
]
