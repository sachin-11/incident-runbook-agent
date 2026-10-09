# scripts/

Ops scripts. All read settings from `IRA_*` env / `.env` and credentials from the AWS profile.

| Script | What it does |
|---|---|
| `verify_model_access.py` | Checks the configured Bedrock models are available. |
| `ingest_kb.py` | Syncs `kb/docs/` to the KB bucket (upload changed, delete removed), starts an ingestion job, waits, exits 1 unless every doc was indexed. `--dry-run` shows the plan. |
| `query_kb.py` | `query_kb.py "<query>" [-k 5] [--service S] [--severity sev1] [--doc-type runbook] [--alert Name] [--json]`: top-k chunks with scores and S3 citations. |
| `teardown.sh` | Destroys the KnowledgeBase stack for a stage and checks nothing is left. |
| `kb_common.py` | Shared: stack name, stack outputs, boto3 clients. |
