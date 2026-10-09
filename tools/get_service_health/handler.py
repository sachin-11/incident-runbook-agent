"""get_service_health(service): status, replicas and health checks."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from tools.common.handler import make_handler
from tools.common.models import ServiceName, ToolInput, ToolOutput
from tools.common.sanitize import TextBudget
from tools.sim.access import backend_for

NAME = "get_service_health"
DESCRIPTION = (
    "Current health of one service: overall status, ready vs desired replicas, individual health "
    "checks and the last restart time. Read-only."
)


class GetServiceHealthInput(ToolInput):
    service: ServiceName = Field(description="Service name, e.g. checkout-api.")


class Check(BaseModel):
    name: str
    status: Literal["passing", "failing", "warning"]
    detail: str


class GetServiceHealthOutput(ToolOutput):
    service: str
    scenario_id: str
    status: Literal["healthy", "degraded", "down"]
    ready_replicas: int
    desired_replicas: int
    checks: list[Check]
    last_restart_at: datetime | None
    notes: str


def get_service_health(req: GetServiceHealthInput) -> GetServiceHealthOutput:
    backend = backend_for(req.service, req.scenario_id)
    health = backend.health(req.service)
    budget = TextBudget(total=4_000)

    def text(value: str) -> str:
        result = budget.take(value, 300)
        return result.text if result else ""

    return GetServiceHealthOutput(
        service=req.service,
        scenario_id=backend.scenario.id,
        status=health.status,
        ready_replicas=health.ready_replicas,
        desired_replicas=health.desired_replicas,
        checks=[
            Check(name=text(c.name), status=c.status, detail=text(c.detail)) for c in health.checks
        ],
        last_restart_at=(
            backend.at(health.last_restart_minutes_ago)
            if health.last_restart_minutes_ago is not None
            else None
        ),
        notes=text(health.notes),
        untrusted_content=bool(budget.flags),
        untrusted_flags=sorted(budget.flags),
    )


handler = make_handler(NAME, GetServiceHealthInput, get_service_health)
