"""Simulated environment behind the tools: services in a healthy state or a failure scenario.

A scenario file (tools/sim/scenarios/<id>.json) overrides parts of a healthy baseline: health,
deploys, extra log lines and metric changes per service. Times are stored as "minutes ago", so a
scenario always looks like it is happening now. Everything is deterministic for a given `now`.
Module 8 replaces this with real chaos injection.
"""

from __future__ import annotations

import json
import math
import zlib
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"
SERVICES = ("checkout-api", "payments-svc", "catalog-api", "orders-worker", "inventory-svc")
LogLevel = Literal["DEBUG", "INFO", "WARN", "ERROR"]
LEVEL_ORDER: dict[str, int] = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}

# metric -> (unit, healthy baseline)
METRICS: dict[str, tuple[str, float]] = {
    "error_rate": ("percent", 0.2),
    "p99_latency_ms": ("ms", 350.0),
    "cpu_pct": ("percent", 35.0),
    "memory_pct": ("percent", 55.0),
    "restarts": ("count_per_min", 0.0),
    "rps": ("requests_per_s", 120.0),
    "db_connections": ("count", 80.0),
    "queue_age_s": ("seconds", 5.0),
}
MetricName = Literal[
    "error_rate",
    "p99_latency_ms",
    "cpu_pct",
    "memory_pct",
    "restarts",
    "rps",
    "db_connections",
    "queue_age_s",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HealthCheck(_Strict):
    name: str
    status: Literal["passing", "failing", "warning"]
    detail: str = ""


class Health(_Strict):
    status: Literal["healthy", "degraded", "down"] = "healthy"
    ready_replicas: int = Field(default=3, ge=0)
    desired_replicas: int = Field(default=3, ge=0)
    checks: tuple[HealthCheck, ...] = (
        HealthCheck(name="readiness", status="passing"),
        HealthCheck(name="liveness", status="passing"),
    )
    last_restart_minutes_ago: int | None = None
    notes: str = ""


class Deploy(_Strict):
    version: str
    minutes_ago: int = Field(ge=0)
    author: str
    summary: str
    status: Literal["succeeded", "in_progress", "failed", "rolled_back"] = "succeeded"


class LogLine(_Strict):
    minutes_ago: float = Field(ge=0)
    level: LogLevel
    message: str


class MetricChange(_Strict):
    """From `since_minutes_ago` on: jump to `value` (step) or move towards it (ramp)."""

    since_minutes_ago: int = Field(ge=1)
    value: float
    shape: Literal["step", "ramp"] = "step"


class ServiceState(_Strict):
    health: Health = Health()
    deploys: tuple[Deploy, ...] | None = None  # None = baseline deploy history
    logs: tuple[LogLine, ...] = ()  # added to the baseline INFO lines
    metrics: dict[MetricName, MetricChange] = Field(default_factory=dict)


class Scenario(_Strict):
    id: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    description: str
    services: dict[str, ServiceState] = Field(default_factory=dict)


def _baseline_deploys(service: str) -> tuple[Deploy, ...]:
    return (
        Deploy(version="2.8.1", minutes_ago=2 * 1440, author="ci-bot", summary="Dependency bumps"),
        Deploy(
            version="2.8.0", minutes_ago=6 * 1440, author="ci-bot", summary=f"{service} release"
        ),
    )


def _baseline_logs(service: str, window_minutes: int) -> list[LogLine]:
    return [
        LogLine(minutes_ago=m, level="INFO", message=f"{service} request summary: ok")
        for m in range(5, window_minutes + 1, 5)
    ]


def _noise(service: str, metric: str, minute: int) -> float:
    """Deterministic +-3% wobble so series look real but tests stay stable."""
    seed = zlib.crc32(f"{service}:{metric}".encode())
    return 1.0 + 0.03 * math.sin(minute / 7.0 + seed % 100)


@cache
def load_scenario(scenario_id: str) -> Scenario:
    path = SCENARIO_DIR / f"{scenario_id}.json"
    if not path.is_file():
        raise KeyError(scenario_id)
    return Scenario.model_validate(json.loads(path.read_text(encoding="utf-8")))


def list_scenarios() -> list[str]:
    return sorted(p.stem for p in SCENARIO_DIR.glob("*.json"))


class SimBackend:
    def __init__(self, scenario: Scenario, now: datetime | None = None) -> None:
        self.scenario = scenario
        self.now = now or datetime.now(UTC)

    def has_service(self, service: str) -> bool:
        return service in SERVICES or service in self.scenario.services

    def _state(self, service: str) -> ServiceState:
        return self.scenario.services.get(service, ServiceState())

    def at(self, minutes_ago: float) -> datetime:
        return self.now - timedelta(minutes=minutes_ago)

    def health(self, service: str) -> Health:
        return self._state(service).health

    def deploys(self, service: str, limit: int) -> list[Deploy]:
        state = self._state(service)
        history = state.deploys if state.deploys is not None else _baseline_deploys(service)
        return sorted(history, key=lambda d: d.minutes_ago)[:limit]

    def logs(self, service: str, window_minutes: int, min_level: str) -> list[LogLine]:
        lines = _baseline_logs(service, window_minutes) + list(self._state(service).logs)
        floor = LEVEL_ORDER[min_level]
        return sorted(
            (
                ln
                for ln in lines
                if ln.minutes_ago <= window_minutes and LEVEL_ORDER[ln.level] >= floor
            ),
            key=lambda ln: ln.minutes_ago,
        )

    def metric(
        self, service: str, metric: MetricName, window_minutes: int, max_points: int = 60
    ) -> list[tuple[int, float]]:
        """(minutes_ago, value) points, oldest first, at most `max_points`."""
        baseline = METRICS[metric][1]
        change = self._state(service).metrics.get(metric)
        step = max(1, math.ceil(window_minutes / max_points))
        points = []
        for minute in range(window_minutes, -1, -step):
            value = baseline
            if change and minute <= change.since_minutes_ago:
                if change.shape == "step":
                    value = change.value
                else:
                    progress = 1 - minute / change.since_minutes_ago
                    value = baseline + (change.value - baseline) * progress
            points.append((minute, round(value * _noise(service, metric, minute), 3)))
        return points
