"""Every tool in one place: used by the OpenAPI generator, the CDK ToolsStack and the tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from tools.get_logs import handler as get_logs
from tools.get_metrics import handler as get_metrics
from tools.get_recent_deploys import handler as get_recent_deploys
from tools.get_service_health import handler as get_service_health
from tools.restart_service import handler as restart_service

ActionGroup = Literal["diagnostics", "remediation"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    action_group: ActionGroup
    risky: bool = False

    @property
    def handler_path(self) -> str:
        """Lambda handler string, relative to the bundle root."""
        return f"tools.{self.name}.handler.handler"


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        get_logs.NAME,
        get_logs.DESCRIPTION,
        get_logs.GetLogsInput,
        get_logs.GetLogsOutput,
        "diagnostics",
    ),
    ToolSpec(
        get_service_health.NAME,
        get_service_health.DESCRIPTION,
        get_service_health.GetServiceHealthInput,
        get_service_health.GetServiceHealthOutput,
        "diagnostics",
    ),
    ToolSpec(
        get_recent_deploys.NAME,
        get_recent_deploys.DESCRIPTION,
        get_recent_deploys.GetRecentDeploysInput,
        get_recent_deploys.GetRecentDeploysOutput,
        "diagnostics",
    ),
    ToolSpec(
        get_metrics.NAME,
        get_metrics.DESCRIPTION,
        get_metrics.GetMetricsInput,
        get_metrics.GetMetricsOutput,
        "diagnostics",
    ),
    ToolSpec(
        restart_service.NAME,
        restart_service.DESCRIPTION,
        restart_service.RestartServiceInput,
        restart_service.RestartServiceOutput,
        "remediation",
        risky=True,
    ),
)

ACTION_GROUPS: tuple[ActionGroup, ...] = ("diagnostics", "remediation")


def tools_in(group: ActionGroup) -> list[ToolSpec]:
    return [t for t in TOOLS if t.action_group == group]
