import json
from typing import Any

import pytest

from observability.logging import current_context, get_logger, log_context


@pytest.fixture(autouse=True)
def _no_xray(monkeypatch):
    monkeypatch.delenv("_X_AMZN_TRACE_ID", raising=False)


def _lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    return [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]


def test_emits_one_json_object_with_extra_fields(capsys):
    log = get_logger("test.json")
    log.info("tool_called", extra={"tool": "get_health", "latency_ms": 12})
    line = capsys.readouterr().out.strip()
    payload = json.loads(line)
    assert payload["message"] == "tool_called"
    assert payload["level"] == "INFO"
    assert payload["tool"] == "get_health"
    assert payload["latency_ms"] == 12
    assert "ts" in payload


def test_get_logger_is_idempotent(capsys):
    get_logger("test.idem")
    log = get_logger("test.idem")
    log.info("once")
    assert len(capsys.readouterr().out.strip().splitlines()) == 1


def test_exception_is_serialized(capsys):
    log = get_logger("test.exc")
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("failed")
    payload = json.loads(capsys.readouterr().out.strip())
    assert "ValueError: boom" in payload["exc_info"]


def test_no_ids_outside_context(capsys):
    get_logger("test.noctx").info("plain")
    (payload,) = _lines(capsys)
    assert "request_id" not in payload
    assert "trace_id" not in payload


def test_context_generates_request_id_and_attaches_to_every_line(capsys):
    log = get_logger("test.ctx")
    with log_context(alert="high-5xx") as bound:
        log.info("first")
        log.info("second")
    log.info("after")
    first, second, after = _lines(capsys)
    assert first["request_id"] == second["request_id"] == bound["request_id"]
    assert len(bound["request_id"]) == 32
    assert first["alert"] == "high-5xx"
    assert "request_id" not in after
    assert current_context() == {}


def test_nested_context_inherits_ids_and_restores(capsys):
    log = get_logger("test.nested")
    with log_context(request_id="req-1", trace_id="trace-1"):
        with log_context(tool="get_logs"):
            log.info("inner")
        log.info("outer")
    inner, outer = _lines(capsys)
    assert (inner["request_id"], inner["trace_id"]) == ("req-1", "trace-1")
    assert inner["tool"] == "get_logs"
    assert (outer["request_id"], outer["trace_id"]) == ("req-1", "trace-1")
    assert "tool" not in outer


def test_trace_id_taken_from_lambda_xray_header(monkeypatch, capsys):
    monkeypatch.setenv("_X_AMZN_TRACE_ID", "Root=1-5759e988-bd862e3fe1be46a994272793;Sampled=1")
    with log_context():
        get_logger("test.xray").info("in_lambda")
    (payload,) = _lines(capsys)
    assert payload["trace_id"] == "1-5759e988-bd862e3fe1be46a994272793"


def test_extra_fields_override_context(capsys):
    with log_context(request_id="req-1"):
        get_logger("test.override").info("x", extra={"request_id": "req-2"})
    (payload,) = _lines(capsys)
    assert payload["request_id"] == "req-2"
