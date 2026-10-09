"""Sync kb/docs/ to the KB's S3 bucket, start an ingestion job and wait for it to finish.

    uv run python scripts/ingest_kb.py [--dry-run] [--timeout 900]

The sync uploads new or changed files (by MD5) and deletes objects no longer in kb/docs/, so the
index never keeps a removed runbook. Exit code 0 only if every document was indexed.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from botocore.exceptions import ClientError

from agent.config import load_kb_settings
from observability.logging import get_logger, log_context
from scripts.kb_common import KbStackOutputs, client, kb_stack_name, load_stack_outputs

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

log = get_logger("ingest_kb")

DOCS_DIR = Path(__file__).resolve().parents[1] / "kb" / "docs"
CONTENT_TYPES = {".md": "text/markdown; charset=utf-8", ".json": "application/json"}
TERMINAL_STATUSES = {"COMPLETE", "FAILED", "STOPPED"}


@dataclass(frozen=True)
class SyncPlan:
    upload: list[str]
    delete: list[str]
    unchanged: int


def local_files(docs_dir: Path, prefix: str) -> dict[str, tuple[Path, str]]:
    """S3 key -> (path, md5) for every .md and .metadata.json file."""
    files: dict[str, tuple[Path, str]] = {}
    for path in sorted(docs_dir.rglob("*")):
        if path.is_file() and path.suffix in CONTENT_TYPES:
            key = prefix + path.relative_to(docs_dir).as_posix()
            files[key] = (path, hashlib.md5(path.read_bytes()).hexdigest())  # noqa: S324 (ETag)
    return files


def plan_sync(local: dict[str, str], remote: dict[str, str]) -> SyncPlan:
    """Compare local key->md5 with remote key->ETag (single-part uploads, so ETag is the MD5)."""
    upload = sorted(k for k, md5 in local.items() if remote.get(k) != md5)
    delete = sorted(k for k in remote if k not in local)
    return SyncPlan(upload=upload, delete=delete, unchanged=len(local) - len(upload))


def remote_etags(s3: S3Client, bucket: str, prefix: str) -> dict[str, str]:
    etags: dict[str, str] = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            etags[obj["Key"]] = obj["ETag"].strip('"')
    return etags


def sync(s3: S3Client, docs_dir: Path, bucket: str, prefix: str, *, dry_run: bool) -> SyncPlan:
    files = local_files(docs_dir, prefix)
    plan = plan_sync({k: md5 for k, (_, md5) in files.items()}, remote_etags(s3, bucket, prefix))
    log.info(
        "sync_plan",
        extra={"upload": len(plan.upload), "delete": len(plan.delete), "unchanged": plan.unchanged},
    )
    if dry_run:
        return plan
    for key in plan.upload:
        path = files[key][0]
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=path.read_bytes(),
            ContentType=CONTENT_TYPES[path.suffix],
        )
    for key in plan.delete:
        s3.delete_object(Bucket=bucket, Key=key)
    return plan


def wait_for_job(agent: Any, kb_id: str, ds_id: str, job_id: str, timeout_s: float) -> Any:
    deadline = time.monotonic() + timeout_s
    while True:
        job = agent.get_ingestion_job(
            knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job_id
        )["ingestionJob"]
        log.info("ingestion_status", extra={"status": job["status"], "job_id": job_id})
        if job["status"] in TERMINAL_STATUSES:
            return job
        if time.monotonic() > deadline:
            raise TimeoutError(f"ingestion job {job_id} still {job['status']} after {timeout_s}s")
        time.sleep(5)


def is_embedding_throttle(exc: ClientError) -> bool:
    """StartIngestionJob test-calls the embedding model; its 429 surfaces as validation."""
    err = exc.response.get("Error", {})
    return err.get("Code") in {"ValidationException", "ThrottlingException"} and (
        "Too many requests" in err.get("Message", "") or err.get("Code") == "ThrottlingException"
    )


def start_job_with_backoff(
    agent: Any,
    out: KbStackOutputs,
    description: str,
    *,
    max_wait_s: float,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Start an ingestion job, retrying with exponential backoff while the model is throttled."""
    delay, waited = 15.0, 0.0
    while True:
        try:
            job = agent.start_ingestion_job(
                knowledgeBaseId=out.knowledge_base_id,
                dataSourceId=out.data_source_id,
                description=description,
            )
            return str(job["ingestionJob"]["ingestionJobId"])
        except ClientError as exc:
            if not is_embedding_throttle(exc) or waited + delay > max_wait_s:
                raise
            log.warning("start_throttled", extra={"retry_in_s": delay, "waited_s": waited})
            sleep(delay)
            waited += delay
            delay = min(delay * 2, 120.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show the sync plan only")
    parser.add_argument("--timeout", type=float, default=900, help="seconds to wait for the job")
    parser.add_argument(
        "--start-timeout",
        type=float,
        default=600,
        help="seconds to keep retrying a throttled job start",
    )
    args = parser.parse_args(argv)

    settings = load_kb_settings()
    with log_context(stage=settings.stage):
        out = load_stack_outputs(client(settings, "cloudformation"), kb_stack_name(settings.stage))
        plan = sync(
            client(settings, "s3"),
            DOCS_DIR,
            out.docs_bucket_name,
            out.docs_prefix,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            return 0

        expected_docs = len(list(DOCS_DIR.rglob("*.md")))
        agent = client(settings, "bedrock-agent")
        job_id = start_job_with_backoff(
            agent,
            out,
            f"sync: {len(plan.upload)} uploaded, {len(plan.delete)} deleted",
            max_wait_s=args.start_timeout,
        )
        job = wait_for_job(agent, out.knowledge_base_id, out.data_source_id, job_id, args.timeout)

        stats = job.get("statistics", {})
        log.info(
            "ingestion_done",
            extra={"status": job["status"], "expected_docs": expected_docs, **stats},
        )
        for reason in job.get("failureReasons", []):
            log.error("ingestion_failure", extra={"reason": reason})

        ok = (
            job["status"] == "COMPLETE"
            and stats.get("numberOfDocumentsFailed", 0) == 0
            and stats.get("numberOfDocumentsScanned", 0) == expected_docs
        )
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
