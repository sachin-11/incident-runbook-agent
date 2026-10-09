# Progress

> This project applies production-grade practices, but they are validated only on a simulated
> environment. It has not been proven in production.

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

### Next
- **Module 1, `tools/`:** a simulated service with chaos injection, plus typed, read-only
  diagnostic Lambdas (logs, health, deploys, metrics) with timeouts and JSON logs. Everything is
  local and free.
