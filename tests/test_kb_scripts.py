import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from scripts.ingest_kb import local_files, plan_sync, start_job_with_backoff
from scripts.kb_common import KbStackOutputs, load_stack_outputs
from scripts.query_kb import build_filter, render, to_hits


def test_plan_sync_uploads_changed_and_new_and_deletes_removed():
    local = {"docs/a.md": "1", "docs/b.md": "2", "docs/c.md": "3"}
    remote = {"docs/a.md": "1", "docs/b.md": "old", "docs/gone.md": "9"}
    plan = plan_sync(local, remote)
    assert plan.upload == ["docs/b.md", "docs/c.md"]
    assert plan.delete == ["docs/gone.md"]
    assert plan.unchanged == 1


def test_local_files_keys_use_prefix_and_posix_paths(tmp_path):
    (tmp_path / "runbooks").mkdir()
    (tmp_path / "runbooks" / "rb.md").write_text("x", encoding="utf-8")
    (tmp_path / "runbooks" / "rb.md.metadata.json").write_text("{}", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    files = local_files(tmp_path, "docs/")
    assert set(files) == {"docs/runbooks/rb.md", "docs/runbooks/rb.md.metadata.json"}
    assert files["docs/runbooks/rb.md"][1] == "9dd4e461268c8034f5c8564e155c67a6"  # md5("x")


def test_build_filter_none_single_and_combined():
    assert build_filter() is None
    assert build_filter(service="checkout-api") == {
        "equals": {"key": "service", "value": "checkout-api"}
    }
    combined = build_filter(doc_type="runbook", alert="KubePodCrashLooping")
    assert combined == {
        "andAll": [
            {"equals": {"key": "doc_type", "value": "runbook"}},
            {"listContains": {"key": "alert_names", "value": "KubePodCrashLooping"}},
        ]
    }


def test_to_hits_and_render_show_score_and_citation():
    results = [
        {
            "content": {"text": "Use this when Kubernetes pods restart repeatedly."},
            "score": 0.71234,
            "location": {"s3Location": {"uri": "s3://b/docs/runbooks/rb-001.md"}},
            "metadata": {"doc_id": "rb-001", "title": "Pods in CrashLoopBackOff"},
        }
    ]
    hits = to_hits(results)
    assert hits[0].rank == 1
    assert hits[0].doc_id == "rb-001"
    out = render("pods restarting", hits)
    assert "score=0.7123" in out
    assert "s3://b/docs/runbooks/rb-001.md" in out


@pytest.fixture
def cfn():
    return boto3.client(
        "cloudformation", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x"
    )


def test_load_stack_outputs(cfn):
    outputs = [
        {"OutputKey": "KnowledgeBaseId", "OutputValue": "KB1"},
        {"OutputKey": "DataSourceId", "OutputValue": "DS1"},
        {"OutputKey": "DocsBucketName", "OutputValue": "bucket"},
        {"OutputKey": "DocsPrefix", "OutputValue": "docs/"},
    ]
    stack = {
        "StackName": "Ira-dev-KnowledgeBase",
        "CreationTime": "2026-10-09T00:00:00Z",
        "StackStatus": "CREATE_COMPLETE",
        "Outputs": outputs,
    }
    with Stubber(cfn) as stub:
        stub.add_response(
            "describe_stacks", {"Stacks": [stack]}, {"StackName": "Ira-dev-KnowledgeBase"}
        )
        out = load_stack_outputs(cfn, "Ira-dev-KnowledgeBase")
    assert (out.knowledge_base_id, out.data_source_id, out.docs_bucket_name) == (
        "KB1",
        "DS1",
        "bucket",
    )


OUT = KbStackOutputs(
    knowledge_base_id="KB", data_source_id="DS", docs_bucket_name="b", docs_prefix="docs/"
)


class _FakeAgent:
    """start_ingestion_job fails `fails` times with the given error, then succeeds."""

    def __init__(
        self, fails: int, code: str = "ValidationException", msg: str = "Too many requests"
    ):
        self.calls = 0
        self.fails = fails
        self.error = ClientError({"Error": {"Code": code, "Message": msg}}, "StartIngestionJob")

    def start_ingestion_job(self, **_: object) -> dict[str, dict[str, str]]:
        self.calls += 1
        if self.calls <= self.fails:
            raise self.error
        return {"ingestionJob": {"ingestionJobId": "JOB1"}}


def test_start_job_retries_throttle_with_backoff():
    sleeps: list[float] = []
    agent = _FakeAgent(fails=3)
    job_id = start_job_with_backoff(agent, OUT, "d", max_wait_s=600, sleep=sleeps.append)
    assert job_id == "JOB1"
    assert sleeps == [15.0, 30.0, 60.0]


def test_start_job_gives_up_after_max_wait():
    agent = _FakeAgent(fails=100)
    with pytest.raises(ClientError):
        start_job_with_backoff(agent, OUT, "d", max_wait_s=50, sleep=lambda _: None)
    assert agent.calls == 3  # waits 15 s + 30 s = 45 s; another 60 s would pass 50 s


def test_start_job_does_not_retry_other_errors():
    agent = _FakeAgent(fails=1, msg="role is not authorized")
    with pytest.raises(ClientError):
        start_job_with_backoff(agent, OUT, "d", max_wait_s=600, sleep=lambda _: None)
    assert agent.calls == 1
