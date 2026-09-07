import logging
import json
import os
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


_HANDLER_MARKER = "syllabicator_handler"
_DEFAULT_MAX_BYTES = 18 * 1024 * 1024
_DEFAULT_BACKUP_COUNT = 3


class MarkdownTraceHandler(logging.Handler):
    """Render live analysis events as readable Markdown sections."""

    def __init__(self, log_path: str | Path):
        super().__init__(level=logging.DEBUG)
        self.log_path = Path(log_path).expanduser().resolve()
        self._lock = threading.RLock()

    def emit(self, record: logging.LogRecord) -> None:
        """Append one real trace event or completion record immediately."""
        event = getattr(record, "analysis_trace_event", None)
        completion = getattr(record, "analysis_trace_complete", None)
        if event is None and completion is None:
            return

        try:
            rendered = (
                _render_trace_event(record, event)
                if event is not None
                else _render_trace_completion(completion)
            )
            with self._lock:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as stream:
                    if self.log_path.stat().st_size == 0:
                        stream.write("# Dynamic Analysis Trace\n\n")
                    stream.write(rendered)
                    stream.write("\n")
        except Exception:
            self.handleError(record)


class LogicDisagreementHandler(RotatingFileHandler):
    """Write sanitized provider/local disagreements as one JSON object per line."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.setFormatter(JsonLineFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "logic_disagreement", None) is None:
            return
        super().emit(record)


def _render_trace_event(record: logging.LogRecord, event: Any) -> str:
    """Render one trace event without losing any execution metadata."""
    if record.getMessage().startswith("analysis_step step=000"):
        header = (
            f"## {datetime.fromtimestamp(record.created).isoformat(sep=' ', timespec='seconds')}"
            f" — `{record.analysis_trace_word}`\n\n"
        )
    else:
        header = ""

    return (
        f"{header}### Step {event.step:03d} — {event.rule} / `{event.node}`\n"
        f"- Input: {_markdown_value(event.input_value)}\n"
        f"- Output: {_markdown_value(event.output_value)}\n"
        f"- Decision: {_markdown_value(event.decision)}\n"
        f"- Resolution: `{event.resolution}`\n"
        f"- Branch: {_markdown_value(event.branch)}\n"
        f"- Repetition: {_markdown_value(event.repetition)}\n"
        f"- Status: {_markdown_value(event.status)}\n\n"
        f"- Skip: {_markdown_value(event.skip)}\n"
        f"- Jump: {_markdown_value(event.jump)}\n"
        f"- Next: {_markdown_value(event.next_node)}\n\n"
    )


def _render_trace_completion(completion: dict[str, Any]) -> str:
    """Render the actual result after the final event has been emitted."""
    return (
        f"### Completed — `{completion['word']}`\n"
        f"- Steps: `{completion['steps']}`\n"
        f"- Result: {_markdown_value(completion['result'])}\n\n"
    )


def _markdown_value(value: Any) -> str:
    """Keep scalar values compact and render structured values as JSON."""
    if value is None:
        return "—"
    if isinstance(value, str):
        return f"`{value}`"
    encoded = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if "\n" not in encoded:
        return f"`{encoded}`"
    indented = "\n".join(f"  {line}" for line in encoded.splitlines())
    return f"\n\n  ```json\n{indented}\n  ```"


def setup_logging(
    log_file: str,
    log_level: str,
    markdown_trace_file: str | None = None,
    disagreement_file: str | None = None,
) -> None:
    """Configure application logging for both the console and a rotating file."""
    logger = logging.getLogger("app")
    level = _resolve_level(log_level)
    log_path = Path(log_file).expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    for handler in logger.handlers[:]:
        if getattr(handler, _HANDLER_MARKER, False):
            logger.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        file_handler = _create_file_handler(log_path)
    except PermissionError:
        fallback_path = log_path.with_name(f"{log_path.stem}.{os.getuid()}{log_path.suffix}")
        file_handler = _create_file_handler(fallback_path)
    console_handler = logging.StreamHandler()
    handlers = [file_handler, console_handler]
    if markdown_trace_file:
        handlers.append(MarkdownTraceHandler(markdown_trace_file))
    if disagreement_file:
        disagreement_path = Path(disagreement_file).expanduser().resolve()
        disagreement_path.parent.mkdir(parents=True, exist_ok=True)
        disagreement_handler = LogicDisagreementHandler(
            disagreement_path,
            maxBytes=_DEFAULT_MAX_BYTES,
            backupCount=_DEFAULT_BACKUP_COUNT,
            encoding="utf-8",
        )
        disagreement_handler.addFilter(lambda record: getattr(record, "logic_disagreement", None) is not None)
        disagreement_handler.setFormatter(JsonLineFormatter())
        handlers.append(disagreement_handler)
    for handler in handlers:
        setattr(handler, _HANDLER_MARKER, True)
        if not isinstance(handler, MarkdownTraceHandler):
            handler.setLevel(level)
        if not isinstance(handler, LogicDisagreementHandler):
            handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(level)
    logger.propagate = True


def _create_file_handler(log_path: Path) -> RotatingFileHandler:
    return RotatingFileHandler(
        log_path,
        maxBytes=_DEFAULT_MAX_BYTES,
        backupCount=_DEFAULT_BACKUP_COUNT,
        encoding="utf-8",
    )


class JsonLineFormatter(logging.Formatter):
    """Serialize only the structured disagreement payload without credentials."""

    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "logic_disagreement", {})
        return json.dumps(
            {"timestamp": datetime.fromtimestamp(record.created).isoformat(), "event": payload},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )


def _resolve_level(log_level: str) -> int:
    level_name = str(log_level).upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise ValueError(f"Unsupported log level: {log_level}")
    return level


__all__ = ["JsonLineFormatter", "LogicDisagreementHandler", "MarkdownTraceHandler", "setup_logging"]
