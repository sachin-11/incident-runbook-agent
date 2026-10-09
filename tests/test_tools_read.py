"""Unit tests for the four read-only tools, called through their Lambda handlers."""

import pytest

import tools.get_logs.handler as get_logs_mod
from tools.common.handler import make_handler
from tools.common.sanitize import TextBudget
from tools.get_logs.handler import handler as get_logs
from tools.get_metrics.handler import handler as get_metrics
from tools.get_recent_deploys.handler import handler as get_recent_deploys
from tools.get_service_health.handler import handler as get_service_health

pytestmark = pytest.mark.usefixtures("fixed_clock")


class Ctx:
    aws_request_id = "lambda-req-1"


def call(handler, **payload):
    return handler(payload, Ctx())


# --- get_logs -----------------------------------------------------------------------------------


def test_get_logs_crashloop_returns_errors_newest_first():
    out = call(
        get_logs, service="checkout-api", level="ERROR", scenario_id="crashloop_after_deploy"
    )
    assert out["returned"] == 4
    assert all(e["level"] == "ERROR" for e in out["entries"])
    assert "DATABASE_URL is missing" in out["entries"][0]["message"]
    timestamps = [e["ts"] for e in out["entries"]]
    assert timestamps == sorted(timestamps, reverse=True)
    assert out["untrusted_content"] is False


def test_get_logs_level_window_and_limit():
    out = call(get_logs, service="checkout-api", level="INFO", window_minutes=60, limit=5)
    assert out["scenario_id"] == "healthy"  # from SIM_SCENARIO_ID
    assert out["total_matched"] == 12  # baseline line every 5 minutes
    assert out["returned"] == 5
    assert out["truncated"] is True
    assert call(get_logs, service="checkout-api", level="ERROR")["returned"] == 0


def test_get_logs_sanitizes_and_flags_injection():
    out = call(get_logs, service="payments-svc", level="ERROR", scenario_id="log_injection")
    flagged = [e for e in out["entries"] if e["flagged"]]
    assert len(flagged) == 1
    assert "\x1b" not in flagged[0]["message"]
    assert "\u200b" not in flagged[0]["message"]
    assert out["untrusted_content"] is True
    assert {"ignore_instructions", "tool_invocation", "credential_bait"} <= set(
        out["untrusted_flags"]
    )


def test_get_logs_caps_total_text(monkeypatch):

    monkeypatch.setattr(get_logs_mod, "TextBudget", lambda: TextBudget(total=60))
    out = call(get_logs, service="checkout-api", level="INFO", window_minutes=600, limit=200)
    assert out["returned"] < out["total_matched"]
    assert out["truncated"] is True


# --- get_service_health -------------------------------------------------------------------------


def test_health_healthy_default():
    out = call(get_service_health, service="catalog-api")
    assert out["status"] == "healthy"
    assert out["ready_replicas"] == out["desired_replicas"] == 3
    assert out["last_restart_at"] is None


def test_health_crashloop_has_failing_checks_and_last_restart():
    out = call(get_service_health, service="checkout-api", scenario_id="crashloop_after_deploy")
    assert out["status"] == "degraded"
    assert (out["ready_replicas"], out["desired_replicas"]) == (2, 3)
    assert any(c["status"] == "failing" for c in out["checks"])
    assert out["last_restart_at"] == "2026-10-09T11:59:00Z"


def test_health_flags_injected_notes():
    out = call(get_service_health, service="payments-svc", scenario_id="log_injection")
    assert out["untrusted_content"] is True
    assert "role_override" in out["untrusted_flags"]


# --- get_recent_deploys -------------------------------------------------------------------------


def test_deploys_newest_first_with_limit():
    out = call(get_recent_deploys, service="checkout-api", scenario_id="crashloop_after_deploy")
    assert [d["version"] for d in out["deploys"]] == ["4.12.0", "4.11.3"]
    assert out["deploys"][0]["status"] == "in_progress"
    assert out["deploys"][0]["minutes_ago"] == 12
    one = call(get_recent_deploys, service="checkout-api", limit=1)
    assert len(one["deploys"]) == 1


def test_deploys_flag_injected_summary():
    out = call(get_recent_deploys, service="payments-svc", scenario_id="log_injection")
    assert out["deploys"][0]["flagged"] is True
    assert "prompt_markup" in out["untrusted_flags"]


# --- get_metrics --------------------------------------------------------------------------------


def test_metrics_baseline_is_flat():
    out = call(get_metrics, service="inventory-svc", metric="error_rate", window_minutes=60)
    assert out["unit"] == "percent"
    assert len(out["points"]) == 61
    assert 0.18 <= out["summary"]["min"] <= out["summary"]["max"] <= 0.22


def test_metrics_show_the_incident():
    out = call(
        get_metrics,
        service="checkout-api",
        metric="db_connections",
        window_minutes=60,
        scenario_id="db_pool_exhaustion",
    )
    assert out["summary"]["first"] < 100
    assert out["summary"]["last"] > 450
    assert out["summary"]["change_pct"] > 400


def test_metrics_downsample_long_windows():
    out = call(
        get_metrics,
        service="catalog-api",
        metric="memory_pct",
        window_minutes=1440,
        scenario_id="memory_leak",
    )
    assert len(out["points"]) <= 61
    assert out["summary"]["last"] > 85  # ramped towards 93%


def test_metrics_zero_baseline_has_no_change_pct():
    out = call(get_metrics, service="catalog-api", metric="restarts")
    assert out["summary"]["change_pct"] is None


# --- shared behaviour ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("handler", "extra"),
    [
        (get_logs, {}),
        (get_service_health, {}),
        (get_recent_deploys, {}),
        (get_metrics, {"metric": "rps"}),
    ],
)
def test_unknown_service_and_scenario_are_tool_errors(handler, extra):
    assert call(handler, service="nope-svc", **extra)["error"]["code"] == "unknown_service"
    out = call(handler, service="checkout-api", scenario_id="does_not_exist", **extra)
    assert out["error"]["code"] == "unknown_scenario"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"service": "Checkout API"},
        {"service": "checkout-api", "window_minutes": 0},
        {"service": "checkout-api", "level": "TRACE"},
        {"service": "checkout-api", "unexpected": 1},
    ],
)
def test_invalid_input_is_rejected(payload):
    out = get_logs(payload, Ctx())
    assert out["error"]["code"] == "invalid_input"


def test_non_dict_event_is_invalid_input():
    assert get_logs("not a dict", Ctx())["error"]["code"] == "invalid_input"  # type: ignore[arg-type]


def test_unexpected_exception_becomes_internal_error(monkeypatch, capsys):

    def boom(_):
        raise RuntimeError("secret detail")

    crashing = make_handler("get_logs", get_logs_mod.GetLogsInput, boom)
    out = crashing({"service": "checkout-api"}, Ctx())
    assert out["error"]["code"] == "internal_error"
    assert "secret detail" not in out["error"]["message"]
    assert "tool_crashed" in capsys.readouterr().out


def test_handler_logs_structured_result(capsys):
    call(get_logs, service="checkout-api")
    lines = [ln for ln in capsys.readouterr().out.splitlines() if '"tool_result"' in ln]
    assert len(lines) == 1
    assert '"tool": "get_logs"' in lines[0]
    assert '"request_id": "lambda-req-1"' in lines[0]
