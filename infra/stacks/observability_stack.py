"""Dashboards, alarms, cost and latency tracking. Empty for now."""

from __future__ import annotations

from typing import Any

from aws_cdk import Stack
from constructs import Construct


class ObservabilityStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)
