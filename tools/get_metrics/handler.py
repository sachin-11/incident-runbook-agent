"""get_metrics(service, metric, window_minutes): a downsampled time series plus a summary."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from tools.common.handler import make_handler
from tools.common.models import ServiceName, ToolInput, ToolOutput
from tools.sim.access import backend_for
from tools.sim.backend import METRICS, MetricName

NAME = "get_metrics"
DESCRIPTION = (
    "Time series for one metric of one service over a window, at most 60 points, plus "
    "min/max/avg/last and the change versus the start of the window. Read-only. Metrics: "
    + ", ".join(METRICS)
    + "."
)


class GetMetricsInput(ToolInput):
    service: ServiceName = Field(description="Service name, e.g. checkout-api.")
    metric: MetricName = Field(description="Metric to read.")
    window_minutes: int = Field(default=60, ge=5, le=1440, description="How far back to look.")


class Point(BaseModel):
    ts: datetime
    value: float


class Summary(BaseModel):
    min: float
    max: float
    avg: float
    last: float
    first: float
    change_pct: float | None = Field(description="Percent change from first to last point.")


class GetMetricsOutput(ToolOutput):
    service: str
    scenario_id: str
    metric: str
    unit: str
    window_minutes: int
    summary: Summary
    points: list[Point]


def get_metrics(req: GetMetricsInput) -> GetMetricsOutput:
    backend = backend_for(req.service, req.scenario_id)
    series = backend.metric(req.service, req.metric, req.window_minutes)
    values = [v for _, v in series]
    first, last = values[0], values[-1]
    return GetMetricsOutput(
        service=req.service,
        scenario_id=backend.scenario.id,
        metric=req.metric,
        unit=METRICS[req.metric][0],
        window_minutes=req.window_minutes,
        summary=Summary(
            min=min(values),
            max=max(values),
            avg=round(sum(values) / len(values), 3),
            last=last,
            first=first,
            change_pct=round((last - first) / first * 100, 1) if first else None,
        ),
        points=[Point(ts=backend.at(m), value=v) for m, v in series],
    )


handler = make_handler(NAME, GetMetricsInput, get_metrics)
