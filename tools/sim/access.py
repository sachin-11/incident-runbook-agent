"""Picks the scenario for a request and checks the service exists in it."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime

from tools.common.models import ToolFailure
from tools.sim.backend import SERVICES, SimBackend, list_scenarios, load_scenario

# Overridable in tests for deterministic timestamps.
clock: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731


def backend_for(service: str, scenario_id: str | None) -> SimBackend:
    sid = scenario_id or os.environ.get("SIM_SCENARIO_ID", "healthy")
    try:
        scenario = load_scenario(sid)
    except KeyError:
        raise ToolFailure(
            "unknown_scenario", f"scenario '{sid}' not found; known: {', '.join(list_scenarios())}"
        ) from None
    backend = SimBackend(scenario, clock())
    if not backend.has_service(service):
        raise ToolFailure(
            "unknown_service", f"service '{service}' not found; known: {', '.join(SERVICES)}"
        )
    return backend
