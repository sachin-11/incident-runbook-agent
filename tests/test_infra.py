import pytest
from aws_cdk import App

from app import build_app


def _stack_names(app: App) -> set[str]:
    return {s.stack_name for s in app.synth().stacks}


def test_synthesizes_four_stacks_for_default_stage(monkeypatch):
    monkeypatch.delenv("IRA_STAGE", raising=False)
    assert _stack_names(build_app(App())) == {
        "Ira-dev-KnowledgeBase",
        "Ira-dev-Tools",
        "Ira-dev-Agent",
        "Ira-dev-Observability",
    }


def test_stage_from_context_prefixes_stacks():
    names = _stack_names(build_app(App(context={"stage": "prod"})))
    assert names == {f"Ira-prod-{n}" for n in ("KnowledgeBase", "Tools", "Agent", "Observability")}


def test_agent_depends_on_kb_and_tools():
    assembly = build_app(App()).synth()
    agent = assembly.get_stack_by_name("Ira-dev-Agent")
    assert {d.id for d in agent.dependencies} >= {"Ira-dev-KnowledgeBase", "Ira-dev-Tools"}


def test_rejects_unknown_stage():
    with pytest.raises(ValueError, match="stage must be one of"):
        build_app(App(context={"stage": "qa"}))
