import boto3
import pytest
from botocore.stub import Stubber

from scripts.verify_model_access import check_model


def _ok(**overrides: object) -> dict[str, object]:
    resp: dict[str, object] = {
        "modelId": "m",
        "agreementAvailability": {"status": "AVAILABLE"},
        "authorizationStatus": "AUTHORIZED",
        "entitlementAvailability": "AVAILABLE",
        "regionAvailability": "AVAILABLE",
    }
    resp.update(overrides)
    return resp


@pytest.fixture
def client():
    # Dummy creds/region: Stubber intercepts before any network call.
    return boto3.client(
        "bedrock", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x"
    )


def test_ready_when_all_available(client):
    with Stubber(client) as stub:
        stub.add_response("get_foundation_model_availability", _ok(), {"modelId": "m"})
        result = check_model(client, "m")
    assert result.ready


def test_not_ready_when_not_authorized(client):
    with Stubber(client) as stub:
        stub.add_response(
            "get_foundation_model_availability",
            _ok(authorizationStatus="NOT_AUTHORIZED"),
            {"modelId": "m"},
        )
        result = check_model(client, "m")
    assert not result.ready
    assert "NOT_AUTHORIZED" in result.detail


def test_client_error_is_reported_not_raised(client):
    with Stubber(client) as stub:
        stub.add_client_error(
            "get_foundation_model_availability", service_error_code="AccessDeniedException"
        )
        result = check_model(client, "m")
    assert not result.ready
    assert "AccessDeniedException" in result.detail
