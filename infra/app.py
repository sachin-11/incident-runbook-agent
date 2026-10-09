"""CDK entry point: `cd infra && cdk synth` (or `make synth`).

The stage comes from `-c stage=...` or IRA_STAGE and prefixes every stack name, so dev, staging
and prod can live in one account. Region and embedding model come from IRA_* env vars or the repo
root .env. Synth needs no AWS credentials.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast, get_args

from aws_cdk import App, Environment, Tags

from agent.config import KbSettings, Stage, load_kb_settings
from stacks import AgentStack, KnowledgeBaseStack, ObservabilityStack, ToolsStack
from stacks.chunking import load_chunking

ROOT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def resolve_stage(app: App, settings: KbSettings) -> Stage:
    raw = app.node.try_get_context("stage") or settings.stage
    if raw not in get_args(Stage):
        raise ValueError(f"stage must be one of {get_args(Stage)}, got {raw!r}")
    return cast(Stage, raw)


def build_app(app: App, settings: KbSettings | None = None) -> App:
    settings = settings or load_kb_settings(ROOT_ENV_FILE)
    stage = resolve_stage(app, settings)
    prefix = f"Ira-{stage}"
    env = Environment(account=os.environ.get("CDK_DEFAULT_ACCOUNT"), region=settings.aws_region)

    kb = KnowledgeBaseStack(
        app,
        f"{prefix}-KnowledgeBase",
        env=env,
        embedding_model_id=settings.embedding_model_id,
        embedding_dimensions=settings.embedding_dimensions,
        chunking=load_chunking(),
    )
    tools = ToolsStack(app, f"{prefix}-Tools", env=env)
    agent = AgentStack(app, f"{prefix}-Agent", env=env)
    agent.add_stack_dependency(kb)
    agent.add_stack_dependency(tools)
    ObservabilityStack(app, f"{prefix}-Observability", env=env).add_stack_dependency(agent)

    Tags.of(app).add("project", "incident-runbook-agent")
    Tags.of(app).add("stage", stage)
    return app


if __name__ == "__main__":
    build_app(App()).synth()
