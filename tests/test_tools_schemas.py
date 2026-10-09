"""OpenAPI schemas: valid, in sync with the models, and real tool output conforms to them."""

import json

import pytest
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate

from scripts.gen_tool_schemas import main as gen_main
from scripts.gen_tool_schemas import render
from tools.get_logs.handler import handler as get_logs_handler
from tools.openapi import build_openapi, schema_path
from tools.registry import ACTION_GROUPS, TOOLS, tools_in
from tools.sim.backend import SERVICES, list_scenarios, load_scenario


@pytest.mark.parametrize("group", ACTION_GROUPS)
def test_committed_schema_matches_models(group):
    assert schema_path(group).read_text(encoding="utf-8") == render(group), (
        "run: uv run python scripts/gen_tool_schemas.py"
    )


def test_check_mode_passes_when_in_sync():
    assert gen_main(["--check"]) == 0


@pytest.mark.parametrize("group", ACTION_GROUPS)
def test_schema_is_valid_openapi(group):
    validate(build_openapi(group))


def test_every_tool_is_in_exactly_one_group():
    names = [
        op["post"]["operationId"]
        for g in ACTION_GROUPS
        for op in build_openapi(g)["paths"].values()
    ]
    assert sorted(names) == sorted(t.name for t in TOOLS)
    assert [t.name for t in tools_in("remediation")] == ["restart_service"]


def test_risky_tool_is_marked_and_requires_fields():
    op = build_openapi("remediation")["paths"]["/restart_service"]["post"]
    assert op["x-requireConfirmation"] == "ENABLED"
    schema = build_openapi("remediation")["components"]["schemas"]["RestartServiceInput"]
    assert set(schema["required"]) == {"service", "reason", "request_id"}


def test_scenario_id_cannot_be_chosen_by_the_model():
    # Outputs echo the scenario for debugging, but no input schema accepts it.
    for tool in TOOLS:
        schema = build_openapi(tool.action_group)["components"]["schemas"][
            tool.input_model.__name__
        ]
        assert "scenario_id" not in json.dumps(schema)


def _validator(group, model_name):
    spec = build_openapi(group)
    root = {"$ref": f"#/components/schemas/{model_name}", "components": spec["components"]}
    return Draft202012Validator(root)


SAMPLES = [
    ("get_logs", {"service": "checkout-api", "level": "ERROR"}),
    ("get_service_health", {"service": "checkout-api"}),
    ("get_recent_deploys", {"service": "checkout-api", "limit": 2}),
    ("get_metrics", {"service": "checkout-api", "metric": "error_rate"}),
]


@pytest.mark.usefixtures("fixed_clock")
@pytest.mark.parametrize(("name", "payload"), SAMPLES)
def test_tool_input_and_output_conform_to_schema(name, payload):
    tool = next(t for t in TOOLS if t.name == name)
    _validator("diagnostics", tool.input_model.__name__).validate(payload)
    module = __import__(f"tools.{name}.handler", fromlist=["handler"])
    out = module.handler({**payload, "scenario_id": "crashloop_after_deploy"}, None)
    _validator("diagnostics", tool.output_model.__name__).validate(out)


@pytest.mark.usefixtures("fixed_clock")
def test_error_output_conforms_to_schema():
    out = get_logs_handler({"service": "nope-svc"}, None)
    _validator("diagnostics", "ToolError").validate(out)


def test_input_schema_rejects_what_the_model_rejects():
    v = _validator("diagnostics", "GetLogsInput")
    assert not v.is_valid({"service": "checkout-api", "window_minutes": 0})
    assert not v.is_valid({"service": "checkout-api", "unknown": 1})


# --- scenarios -----------------------------------------------------------------------------------


@pytest.mark.parametrize("scenario_id", list_scenarios())
def test_scenario_files_are_valid(scenario_id):
    scenario = load_scenario(scenario_id)
    assert scenario.id == scenario_id
    assert set(scenario.services) <= set(SERVICES)


def test_expected_scenarios_exist():
    assert {
        "healthy",
        "crashloop_after_deploy",
        "db_pool_exhaustion",
        "memory_leak",
        "log_injection",
    } <= set(list_scenarios())
