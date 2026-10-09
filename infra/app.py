"""CDK entry point: `cd infra && cdk synth` (or `make synth`).

The stage comes from `-c stage=...` or IRA_STAGE and prefixes every stack name, so dev, staging
and prod can live in one account. No account/region is pinned here, so synth needs no credentials.
"""

from __future__ import annotations

import os
from typing import cast, get_args

from aws_cdk import App, Tags

from agent.config import Stage
from stacks import AgentStack, KnowledgeBaseStack, ObservabilityStack, ToolsStack


def resolve_stage(app: App) -> Stage:
    raw = app.node.try_get_context("stage") or os.environ.get("IRA_STAGE", "dev")
    if raw not in get_args(Stage):
        raise ValueError(f"stage must be one of {get_args(Stage)}, got {raw!r}")
    return cast(Stage, raw)


def build_app(app: App) -> App:
    stage = resolve_stage(app)
    prefix = f"Ira-{stage}"

    kb = KnowledgeBaseStack(app, f"{prefix}-KnowledgeBase")
    tools = ToolsStack(app, f"{prefix}-Tools")
    agent = AgentStack(app, f"{prefix}-Agent")
    agent.add_stack_dependency(kb)
    agent.add_stack_dependency(tools)
    ObservabilityStack(app, f"{prefix}-Observability").add_stack_dependency(agent)

    Tags.of(app).add("project", "incident-runbook-agent")
    Tags.of(app).add("stage", stage)
    return app


if __name__ == "__main__":
    build_app(App()).synth()
