import json

from observability.logging import get_logger


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
