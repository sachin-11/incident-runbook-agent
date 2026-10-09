"""Turns a typed tool function into a Lambda handler.

The event is the tool's arguments as a JSON object: the shape AgentCore Gateway sends to a Lambda
target, and what a direct `lambda invoke` sends. The handler validates input with the tool's
pydantic model, runs the tool inside a log context, and always returns a JSON object: the tool's
output, or `{"error": {"code", "message"}}`.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from observability.logging import get_logger, log_context
from tools.common.models import ToolError, ToolErrorBody, ToolFailure, ToolInput, ToolOutput
from tools.common.sanitize import clean

LambdaHandler = Callable[[dict[str, Any], Any], dict[str, Any]]


def error(code: str, message: str) -> dict[str, Any]:
    return ToolError(error=ToolErrorBody(code=code, message=clean(message)[:300])).model_dump()


def _validation_message(exc: ValidationError) -> str:
    parts = [f"{'.'.join(str(p) for p in e['loc']) or 'input'}: {e['msg']}" for e in exc.errors()]
    return "; ".join(parts)


def make_handler[I: ToolInput, O: ToolOutput](
    name: str, input_model: type[I], fn: Callable[[I], O]
) -> LambdaHandler:
    log = get_logger(f"tools.{name}", os.environ.get("LOG_LEVEL", "INFO"))

    def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
        started = time.perf_counter()
        lambda_request_id = getattr(context, "aws_request_id", None)
        with log_context(request_id=lambda_request_id, tool=name):
            out: dict[str, Any]
            try:
                payload = input_model.model_validate(event if isinstance(event, dict) else {})
            except ValidationError as exc:
                out = error("invalid_input", _validation_message(exc))
            else:
                try:
                    out = fn(payload).model_dump(mode="json")
                except ToolFailure as exc:
                    out = error(exc.code, exc.message)
                except Exception:
                    log.exception("tool_crashed")
                    out = error("internal_error", f"{name} failed; see logs")
            log.info(
                "tool_result",
                extra={
                    "ok": "error" not in out,
                    "error_code": out.get("error", {}).get("code"),
                    "untrusted_content": out.get("untrusted_content", False),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            return out

    return handler
