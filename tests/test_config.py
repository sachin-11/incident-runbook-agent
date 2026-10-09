import pytest
from pydantic import ValidationError

from agent.config import Settings, load_settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    # Ignore any developer .env and IRA_* vars from the real shell.
    monkeypatch.chdir(tmp_path)
    for key in ("IRA_AWS_REGION", "IRA_AGENT_MODEL_ID", "IRA_EMBEDDING_MODEL_ID", "IRA_ENV"):
        monkeypatch.delenv(key, raising=False)


def test_loads_from_env(monkeypatch):
    monkeypatch.setenv("IRA_AWS_REGION", "eu-west-1")
    monkeypatch.setenv("IRA_AGENT_MODEL_ID", "agent-model")
    monkeypatch.setenv("IRA_EMBEDDING_MODEL_ID", "embed-model")
    s = load_settings()
    assert (s.aws_region, s.agent_model_id, s.embedding_model_id) == (
        "eu-west-1",
        "agent-model",
        "embed-model",
    )
    assert s.env == "dev"


def test_missing_region_and_models_fail():
    with pytest.raises(ValidationError) as exc:
        load_settings()
    missing = {e["loc"][0] for e in exc.value.errors()}
    assert missing == {"aws_region", "agent_model_id", "embedding_model_id"}


def test_rejects_unknown_env(monkeypatch):
    monkeypatch.setenv("IRA_AWS_REGION", "us-east-1")
    monkeypatch.setenv("IRA_AGENT_MODEL_ID", "a")
    monkeypatch.setenv("IRA_EMBEDDING_MODEL_ID", "e")
    monkeypatch.setenv("IRA_ENV", "qa")
    with pytest.raises(ValidationError):
        Settings()
