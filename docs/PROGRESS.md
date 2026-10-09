# Progress

> This project applies production-grade practices, but they are validated only on a simulated
> environment. It has not been proven in production.

## Module 2: Knowledge Base (blocked on a Bedrock quota, 2026-10-09)

### Done
- **Content:** 20 runbooks and 6 postmortems in `kb/docs/`, each with a `.md.metadata.json` file
  holding `doc_id`, `doc_type`, `title`, `service`, `severity` and `alert_names`. They cover pod
  crashloop, latency, DB connection exhaustion, OOM, bad deploy, disk full, cache stampede, queue
  backlog, cert expiry, DNS, 5xx, third-party 429s, DynamoDB throttling, HPA maxed, replica lag,
  lock contention, auth/JWKS, circuit breaker, feature flags and node NotReady.
- **KnowledgeBaseStack:** a docs S3 bucket, an S3 Vectors bucket and index (1024 dims, cosine, Bedrock
  text and metadata keys marked non-filterable), the Bedrock KB (Titan Text Embeddings V2, read from
  `IRA_EMBEDDING_MODEL_ID`), and an S3 data source. The KB role is scoped to that model, the bucket
  and the index.
- **Chunking:** `kb/chunking.yaml` (v1: FIXED_SIZE, 300 tokens, 15% overlap), validated by
  `infra/stacks/chunking.py`. The data source is named `docs-chunking-v<version>`, so changing the
  chunking replaces it.
- **Scripts:** `ingest_kb.py` (MD5-based sync with deletes, ingestion job, polling, and a check that
  every doc was indexed), `query_kb.py` (top-k, scores, S3 citations, filters on service, severity,
  doc type and alert) and `teardown.sh`. Makefile targets: `deploy-kb`, `ingest`, `query`,
  `teardown-kb`.
- **Config:** `KbSettings` is the subset of settings the infra and KB scripts need, so they run
  without an agent model. `Settings` extends it.
- **Tests:** 97 passing. They cover the doc template and metadata (sections in order, alert lists
  match the metadata, metadata under 1 KB), chunking, the KB stack template, and the script helpers.

### Acceptance checks
- `cdk deploy`: done, now in **ap-south-1**. CDK was bootstrapped in 964775859218 for us-east-1
  and ap-south-1. Outputs: `KnowledgeBaseId=JCKNXESBPP`, `DataSourceId=3C47ANWKBD`,
  `DocsBucketName=ira-dev-knowledgebase-docsbucketecea003f-th2m4vqod4oe`, `ChunkingVersion=1`.
  The first deploy in us-east-1 was torn down with `scripts/teardown.sh`.
- `ingest_kb.py`: **blocked by Bedrock throttling on the account.** The S3 sync works (52 files).
  `StartIngestionJob` fails with a 429 from Titan Text Embeddings V2.
  - In us-east-1, Service Quotas shows 0 RPM and 0 TPM for every on-demand model.
  - In ap-south-1 and eu-west-1, Service Quotas shows the normal 6000 RPM and 300K TPM, but in
    practice only the first `invoke-model` call succeeds and every call after it is throttled.
    That points to an undocumented new-account limit applied in every region, so switching
    region does not fix it. It needs an AWS Support case.
- The query checks (pods-restarting query and the 5-query miss analysis) are **pending** until
  ingestion works.
- pytest: passing (97 tests).

### Vector store choice and cost
- **S3 Vectors.** It is GA with Bedrock KB, has no idle cost and is billed per use. Rejected
  OpenSearch Serverless because it has a fixed monthly OCU minimum of hundreds of dollars. Rejected
  Aurora pgvector because it needs a cluster to run and more parts.
- **Monthly estimate at this size** (26 docs, about 120 chunks, under 1 MB of vectors): under
  $0.05. That covers S3 Vectors storage ($0.06/GB-month), PUTs ($0.20/GB), queries ($0.0025 per
  1,000 plus data processed), Titan v2 embeddings (about $0.001 per full re-ingest; rate not
  verified), and S3 standard for the docs (about $0).

### Decisions
- **The agent layer moves to Amazon Bedrock AgentCore (2026-10-09).** Runtime hosts a Strands
  agent, Gateway exposes the Lambda tools, Policy (Cedar) enforces read-only use and approvals,
  and Memory, Observability and Evaluations cover AgentOps. The KB design does not change. Docs
  updated: `CLAUDE.md`, `README.md`, `docs/ARCHITECTURE.md`, and the `agent/`, `tools/` and
  `infra/` READMEs. Nothing has been built for it yet; that starts in the agent module.
- `ingest_kb.py` now retries a throttled `StartIngestionJob` with exponential backoff (15 s
  doubling to 120 s, up to `--start-timeout`, default 600 s). The live run was still throttled
  for all 10 minutes.
- An account probe found 1 successful `invoke-model` call per region, then throttling for 30+
  minutes. A trickle ingest (embed ourselves and write vectors directly) would take days, and
  queries need embeddings too, so it was not pursued.

### Known gaps
- The Bedrock throttling (above) is the main blocker. It needs an AWS Support case to lift the limit on
  this new account.
- `numberOfDocumentsScanned` on a re-ingest with no changes hasn't been verified yet. The success
  check may need adjusting after the first real run.
- The deployed KB costs about $0 while idle. Remove it with `scripts/teardown.sh` if needed.

### Next
- Once quotas are raised: run `make ingest`, run the query checks, record the retrieval results here.

## Module 1: Foundation (done, 2026-10-09)

Builds on Module 0. No AWS resources are created.

### Done
- Every folder has a README stub. Added `CLAUDE.md`, `docs/ARCHITECTURE.md` (text diagram) and
  `Makefile` (`install lint typecheck test format`, plus `synth precommit check`).
- **Config:** `Settings` now covers the KB ID, agent ID and alias ID (optional until deployed),
  `stage` (`dev|staging|prod`, was `env`), budget caps (tokens and USD per incident, USD per month)
  and timeouts (tool and agent, capped at Lambda's 900 s). `.env.example` lists every key.
- **Logging:** `log_context()` binds `request_id` (generated when missing) and `trace_id` (from
  Lambda's `_X_AMZN_TRACE_ID` root when present) to every line in a block. Nested blocks inherit
  the ids. It uses contextvars, so it is safe with threads and asyncio.
- **CDK:** `infra/` holds the app plus empty `KnowledgeBaseStack`, `ToolsStack`, `AgentStack` and
  `ObservabilityStack`, named `Ira-<stage>-*`, with dependencies KB+Tools -> Agent ->
  Observability and tags `project` and `stage`. `aws-cdk-lib` and `constructs` sit in a separate
  `infra` dependency group.
- **pre-commit:** standard hygiene hooks (including private-key and AWS-credential detection), plus
  ruff and mypy run via `uv run`, so their versions come from `uv.lock`.
- **CI:** the `lint-type-test` job runs `make lint`, `make typecheck` and `make test`. A new
  `cdk-synth` job runs `make synth`. Both run on PRs and on pushes to `main`.
- **Tests:** 24 in total, covering config (9), logging (8), infra synth (4) and model access (3).
- `.gitattributes` forces LF line endings so Windows checkouts pass the pre-commit hooks.

### Acceptance checks (2026-10-09, Windows 11)
- `make lint && make typecheck && make test`: all green (24 passed).
- `cd infra && npx aws-cdk@2 synth`: synthesizes all 4 stacks.
- `pre-commit run --all-files`: all hooks pass.

### Decisions
- **No global CDK CLI.** The CLI runs through `npx aws-cdk@2`, so the only machine requirement is
  Node. The Python construct library is pinned by `uv.lock`.
- **Stage comes from `-c stage=` or `IRA_STAGE`, not from `Settings`.** That way synth works in CI
  without model IDs.
- **No account or region is pinned in the stacks yet.** Synth needs no credentials. Pinning
  happens when a stack first needs a lookup.
- **Pinning:** `pyproject.toml` holds compatible ranges and `uv.lock` holds exact versions. CI uses
  `uv sync --locked`.

### Known gaps
- `CLAUDE.md` was written from README and docs, because the original master prompt was not
  available here. It has a TODO to paste the prompt in verbatim.
- CDK reports 84 feature flags that are not configured. That doesn't matter for empty stacks, but
  review it with `cdk flags` before the first real resources go in.
- On Windows, `make` is from `ezwinports.make`. The jsii kernel sometimes prints a harmless
  `ENOTEMPTY` temp-cleanup error when a process exits.
- CI still hasn't run on GitHub because the repo has no remote yet.

### Next
- Module 2, as defined in the master prompt. Not started.

## Module 0: Repo scaffold (done, 2026-10-09)

### Done
- Repo layout: `agent/ tools/ kb/ evals/ infra/ observability/ scripts/ tests/ docs/ .github/`
- uv project (Python 3.12) with a `uv.lock` lockfile. Tooling: ruff (lint and format), mypy in
  strict mode with the pydantic plugin, and pytest.
- `agent/config.py` holds the typed settings (pydantic-settings, `IRA_` prefix). Region and model
  IDs are required env vars and have no defaults in code.
- `observability/logging.py` writes structured JSON logs (one object per line, plus any `extra`
  fields and the exception text when there is one).
- `scripts/verify_model_access.py` calls `bedrock:GetFoundationModelAvailability`. I checked the API
  shape against the service model in botocore 1.43.110.
- CI (`.github/workflows/ci.yml`) runs ruff, a format check, mypy and pytest.
- `.env.example` is committed. Credentials come only from the AWS profile.

### Decisions
- **uv** over pip-tools: it was already installed, it's faster, and it gives us a lockfile.
- Shared settings live in `agent/config.py` and logging in `observability/`, so the layout gets no
  new top-level directories. The Lambda bundles in Module 1 will need to include `observability/`.
- CDK dependencies come later, with the infra module, to keep Module 0 lightweight.

### Known gaps
- `verify_model_access.py` has not been run against real AWS yet, because no profile or region is
  configured. It is covered only by Stubber tests.
- I haven't verified whether `GetFoundationModelAvailability` accepts **inference-profile IDs**
  (for example `us.`-prefixed IDs). Check this when the model is chosen.
- CI hasn't run on GitHub yet because the repo has no remote.
