"""get_recent_deploys(service, limit): deploy history, newest first."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from tools.common.handler import make_handler
from tools.common.models import ServiceName, ToolInput, ToolOutput
from tools.common.sanitize import TextBudget
from tools.sim.access import backend_for

NAME = "get_recent_deploys"
DESCRIPTION = (
    "Recent deploys of one service, newest first: version, time, author, change summary and "
    "rollout status. Read-only. Use it to check whether a problem started with a release."
)


class GetRecentDeploysInput(ToolInput):
    service: ServiceName = Field(description="Service name, e.g. checkout-api.")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum number of deploys.")


class DeployRecord(BaseModel):
    version: str
    deployed_at: datetime
    minutes_ago: int
    author: str
    summary: str
    status: str
    flagged: bool


class GetRecentDeploysOutput(ToolOutput):
    service: str
    scenario_id: str
    deploys: list[DeployRecord]


def get_recent_deploys(req: GetRecentDeploysInput) -> GetRecentDeploysOutput:
    backend = backend_for(req.service, req.scenario_id)
    budget = TextBudget(total=4_000)
    records = []
    for d in backend.deploys(req.service, req.limit):
        summary = budget.take(d.summary, 300)
        author = budget.take(d.author, 80)
        if summary is None or author is None:
            break
        records.append(
            DeployRecord(
                version=d.version[:40],
                deployed_at=backend.at(d.minutes_ago),
                minutes_ago=d.minutes_ago,
                author=author.text,
                summary=summary.text,
                status=d.status,
                flagged=bool(summary.flags or author.flags),
            )
        )
    return GetRecentDeploysOutput(
        service=req.service,
        scenario_id=backend.scenario.id,
        deploys=records,
        untrusted_content=bool(budget.flags),
        untrusted_flags=sorted(budget.flags),
    )


handler = make_handler(NAME, GetRecentDeploysInput, get_recent_deploys)
