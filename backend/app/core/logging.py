"""Structured logging (Phase 8, FR-26).

A thin wrapper over the stdlib `logging` that emits one key=value structured
line per event: request_id (set by the http middleware), and for agent work,
session_id/task_id. Keeps the log greppable and machine-parseable without
adding a dependency.

Usage:
    logger = get_logger(__name__)
    logger.info("agent run", extra={"session_id": ..., "task_id": ...})
"""

import logging
import sys

from typing import Any

_configured = False


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger once (safe to call repeatedly)."""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _configured = True


class StructuredFormatter(logging.Formatter):
    """key=value formatter; includes extra fields like request_id."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key
            not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "taskName",
                "message",
            }
        }
        if not extras:
            return base
        suffix = " ".join(f"{k}={v}" for k, v in extras.items())
        return f"{base} | {suffix}"


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_agent_run(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    request_id: str | None,
    session_id: Any = None,
    task_id: Any = None,
    **extra: Any,
) -> None:
    """Structured agent log with request/session/task ids (FR-26)."""
    fields = dict(extra)
    if request_id:
        fields["request_id"] = request_id
    if session_id:
        fields["session_id"] = session_id
    if task_id:
        fields["task_id"] = task_id
    logger.log(level, message, extra=fields)