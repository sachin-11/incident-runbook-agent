import os

import pytest
from pydantic import ValidationError

from agent.config import Settings, load_settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    # Ignore any developer .env and IRA_* vars from the real shell.
    monkeypatch.chdir(tmp_path)
    for key in [k for k in os.environ if k.startswith("IRA_")]:
        monkeypatch.delenv(key)


@pytest.fixture
def required_env(monkeypatch):
    monkeypatch.setenv("IRA_AWS_REGION", "eu-west-1")
    monkeypatch.setenv("IRA_AGENT_MODEL_ID", "agent-model")
    monkeypatch.setenv("IRA_EMBEDDING_MODEL_ID", "embed-model")


@pytest.mark.usefixtures("required_env")
def test_loads_from_env_with_defaults():
    s = load_settings()
    assert (s.aws_region, s.agent_model_id, s.embedding_model_id) == (
        "eu-west-1",
        "agent-model",
        "embed-model",
    )
    assert s.stage == "dev"
    assert s.knowledge_base_id is None
    assert s.agent_id is None
    assert s.agent_alias_id is None
    assert s.max_tokens_per_incident > 0
    assert 0 < s.tool_timeout_s <= s.agent_timeout_s


def test_missing_region_and_models_fail():
    with pytest.raises(ValidationError) as exc:
        load_settings()
    missing = {e["loc"][0] for e in exc.value.errors()}
    assert missing == {"aws_region", "agent_model_id", "embedding_model_id"}


@pytest.mark.usefixtures("required_env")
def test_overrides_ids_budgets_and_timeouts(monkeypatch):
    monkeypatch.setenv("IRA_STAGE", "prod")
    monkeypatch.setenv("IRA_KNOWLEDGE_BASE_ID", "KB123")
    monkeypatch.setenv("IRA_AGENT_ID", "AG123")
    monkeypatch.setenv("IRA_AGENT_ALIAS_ID", "AL123")
    monkeypatch.setenv("IRA_MAX_COST_USD_PER_INCIDENT", "1.25")
    monkeypatch.setenv("IRA_TOOL_TIMEOUT_S", "5")
    s = load_settings()
    assert s.stage == "prod"
    assert (s.knowledge_base_id, s.agent_id, s.agent_alias_id) == ("KB123", "AG123", "AL123")
    assert s.max_cost_usd_per_incident == 1.25
    assert s.tool_timeout_s == 5.0


@pytest.mark.usefixtures("required_env")
def test_reads_dotenv_file(tmp_path):
    (tmp_path / ".env").write_text("IRA_STAGE=staging\n", encoding="utf-8")
    assert load_settings().stage == "staging"


@pytest.mark.usefixtures("required_env")
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("IRA_STAGE", "qa"),
        ("IRA_MAX_TOKENS_PER_INCIDENT", "0"),
        ("IRA_MONTHLY_BUDGET_USD", "-1"),
        ("IRA_TOOL_TIMEOUT_S", "901"),
        ("IRA_KNOWLEDGE_BASE_ID", ""),
    ],
)
def test_rejects_invalid_values(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError):
        Settings()
