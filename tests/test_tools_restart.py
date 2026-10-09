"""restart_service: approval, idempotency, replay protection, dry run and audit trail.

DynamoDB is mocked with moto, so conditional transactions behave like the real service.
"""

import json
import time

import boto3
import pytest
from moto import mock_aws

import tools.restart_service.handler as restart
from tools.common.approval import issue_token
from tools.common.audit import AuditStore

KEY = b"test-signing-key" * 4
TABLE = "audit-test"


class Ctx:
    aws_request_id = "lambda-req-1"


@pytest.fixture
def ddb(monkeypatch, fixed_clock):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        store = AuditStore(TABLE, client)
        monkeypatch.setattr(restart, "audit_store", lambda: store)
        monkeypatch.setattr(restart, "signing_key", lambda: KEY)
        yield client


def token(service="checkout-api", ttl_s=900, now=None):
    return issue_token(KEY, service=service, approver="dana", ttl_s=ttl_s, now=now)


def call(**payload):
    payload.setdefault("service", "checkout-api")
    payload.setdefault("reason", "Pods crashlooping after deploy 4.12.0")
    payload.setdefault("request_id", "req-0001")
    return restart.handler(payload, Ctx())


def events(client, outcome=None):
    items = client.scan(TableName=TABLE)["Items"]
    evts = [json.loads(i["body"]["S"]) for i in items if i["pk"]["S"].startswith("evt#")]
    return [e for e in evts if outcome is None or e["outcome"] == outcome]


# --- rejections ----------------------------------------------------------------------------------


def test_no_token_is_rejected_and_audited(ddb):
    out = call()
    assert out["status"] == "rejected"
    assert out["reason_code"] == "missing_token"
    assert out["audit_event_id"]
    (evt,) = events(ddb)
    assert (evt["outcome"], evt["reason_code"], evt["service"]) == (
        "rejected",
        "missing_token",
        "checkout-api",
    )


def test_expired_token_is_rejected(ddb):
    out = call(approval_token=token(ttl_s=60, now=time.time() - 120))
    assert (out["status"], out["reason_code"]) == ("rejected", "expired")


def test_forged_token_is_rejected(ddb):
    forged = issue_token(b"attacker-key", service="checkout-api", approver="evil")
    assert call(approval_token=forged)["reason_code"] == "bad_signature"


def test_token_for_other_service_is_rejected(ddb):
    assert call(approval_token=token("payments-svc"))["reason_code"] == "wrong_service"


def test_replayed_token_is_rejected(ddb):
    t = token()
    assert call(approval_token=t, request_id="req-0001")["status"] == "restarted"
    out = call(approval_token=t, request_id="req-0002")
    assert (out["status"], out["reason_code"]) == ("rejected", "token_replayed")
    assert events(ddb, "rejected")[0]["reason_code"] == "token_replayed"


def test_request_id_reused_with_other_input_is_conflict(ddb):
    call(approval_token=token())
    out = call(approval_token=token(), reason="A completely different reason here")
    assert (out["status"], out["reason_code"]) == ("rejected", "idempotency_conflict")


def test_unknown_service_and_bad_input(ddb):
    assert call(service="nope-svc", approval_token=token("nope-svc"))["error"]["code"] == (
        "unknown_service"
    )
    assert call(reason="short")["error"]["code"] == "invalid_input"
    assert call(request_id="bad id!")["error"]["code"] == "invalid_input"


# --- success and idempotency ---------------------------------------------------------------------


def test_valid_token_restarts_and_audits(ddb):
    out = call(approval_token=token(), scenario_id="crashloop_after_deploy")
    assert out["status"] == "restarted"
    assert out["approver"] == "dana"
    assert out["simulated"] is True
    assert "2/3 ready" in out["message"]
    (evt,) = events(ddb, "restarted")
    assert evt["approver"] == "dana"
    assert evt["jti"]
    pks = {i["pk"]["S"].split("#")[0] for i in ddb.scan(TableName=TABLE)["Items"]}
    assert pks == {"req", "tok", "evt"}


def test_same_request_id_returns_same_result(ddb):
    t = token()
    first = call(approval_token=t)
    again = call(approval_token=t)
    assert again["status"] == "restarted"
    assert again["idempotent_replay"] is True
    assert again["message"] == first["message"]
    assert again["audit_event_id"] != first["audit_event_id"]
    # A retry succeeds even after the token expired: the request already happened.
    later = call(approval_token=None)
    assert later["idempotent_replay"] is True
    assert len(events(ddb, "idempotent_replay")) == 2


def test_lost_race_with_own_retry_returns_stored_result(ddb, monkeypatch):
    store = restart.audit_store()
    t = token()
    first = call(approval_token=t)
    # Simulate: our pre-check missed the stored request, then the claim collides with it.
    monkeypatch.setattr(store, "get_request", _miss_once(store.get_request))
    out = call(approval_token=t)
    assert out["idempotent_replay"] is True
    assert out["message"] == first["message"]


def _miss_once(real):
    calls = {"n": 0}

    def fake(request_id):
        calls["n"] += 1
        return None if calls["n"] == 1 else real(request_id)

    return fake


# --- dry run -------------------------------------------------------------------------------------


def test_dry_run_without_token_reports_would_not_execute(ddb):
    out = call(dry_run=True)
    assert (out["status"], out["would_execute"], out["reason_code"]) == (
        "dry_run",
        False,
        "missing_token",
    )


def test_dry_run_with_bad_token_reports_reason(ddb):
    out = call(dry_run=True, approval_token=token("payments-svc"))
    assert (out["would_execute"], out["reason_code"]) == (False, "wrong_service")


def test_dry_run_does_not_consume_token(ddb):
    t = token()
    dry = call(dry_run=True, approval_token=t)
    assert (dry["status"], dry["would_execute"]) == ("dry_run", True)
    assert "Would restart checkout-api" in dry["message"]
    assert call(approval_token=t)["status"] == "restarted"
    used = call(dry_run=True, approval_token=t, request_id="req-0009")
    assert (used["would_execute"], used["reason_code"]) == (False, "token_replayed")
    assert len(events(ddb, "dry_run")) == 2


# --- wiring --------------------------------------------------------------------------------------


def test_signing_key_and_store_come_from_env(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        arn = boto3.client("secretsmanager").create_secret(Name="k", SecretString="s3cret")["ARN"]
        monkeypatch.setenv("APPROVAL_SECRET_ARN", arn)
        monkeypatch.setenv("AUDIT_TABLE", "t")
        restart.signing_key.cache_clear()
        restart.audit_store.cache_clear()
        try:
            assert restart.signing_key() == b"s3cret"
            assert restart.audit_store().table == "t"
        finally:
            restart.signing_key.cache_clear()
            restart.audit_store.cache_clear()
