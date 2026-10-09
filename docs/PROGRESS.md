# Progress

> This project applies production-grade practices, but they are validated only on a simulated
> environment. It has not been proven in production.

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
