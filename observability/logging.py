"""Structured JSON logging shared by the agent and every Lambda tool.

Use `log_context()` around a unit of work (one alert, one Lambda invocation) so every log line
inside it carries the same `request_id` and `trace_id`.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Attributes every LogRecord has; anything else was passed via `extra=` and is emitted.
_STANDARD_ATTRS = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys() | {"message", "asctime"}
)

# Fields attached to every record emitted inside `log_context()`. Safe across threads and asyncio.
_context: ContextVar[dict[str, str]] = ContextVar("ira_log_context")


def _xray_trace_id() -> str | None:
    """Root trace id from Lambda's `_X_AMZN_TRACE_ID` ("Root=1-...;Parent=...;Sampled=1")."""
    header = os.environ.get("_X_AMZN_TRACE_ID", "")
    for part in header.split(";"):
        key, _, value = part.partition("=")
        if key == "Root" and value:
            return value
    return None


def current_context() -> dict[str, str]:
    """A copy of the fields bound by the enclosing `log_context()` blocks."""
    return dict(_context.get({}))


@contextmanager
def log_context(
    *, request_id: str | None = None, trace_id: str | None = None, **fields: str
) -> Iterator[dict[str, str]]:
    """Bind request/trace ids (and any extra fields) to every log line in this block.

    Ids are inherited from an enclosing block. Otherwise a new `request_id` is generated and the
    `trace_id` is taken from the X-Ray header when running in Lambda.
    """
    outer = _context.get({})
    bound = {**outer, **fields}
    bound["request_id"] = request_id or outer.get("request_id") or uuid.uuid4().hex
    resolved_trace = trace_id or outer.get("trace_id") or _xray_trace_id()
    if resolved_trace:
        bound["trace_id"] = resolved_trace
    token = _context.set(bound)
    try:
        yield dict(bound)
    finally:
        _context.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **_context.get({}),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _StdoutHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Writes to whatever sys.stdout is at emit time (works with redirection and test capture)."""

    @property
    def stream(self) -> Any:
        return sys.stdout

    @stream.setter
    def stream(self, _: Any) -> None:
        pass


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Return a logger that writes one JSON object per line to stdout. Idempotent."""
    logger = logging.getLogger(name)
    if not any(isinstance(h.formatter, JsonFormatter) for h in logger.handlers):
        handler = _StdoutHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger
