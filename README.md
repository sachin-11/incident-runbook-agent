# Incident Runbook Agent

An AI agent on AWS that helps handle service incidents. It runs on **Amazon Bedrock AgentCore**.
When an alert arrives it:

1. Retrieves relevant runbooks and postmortems from an Amazon Bedrock Knowledge Base and cites them.
2. Runs safe, read-only diagnostics: Lambda tools (logs, health, deploys, metrics) exposed through
   AgentCore Gateway.
3. Proposes a fix and asks a human for approval before any risky action. AgentCore Policy blocks
   state-changing tools that have not been approved.

The AgentOps layer covers tracing (AgentCore Observability), evals with a CI gate (RAGAS and
AgentCore Evaluations), guardrails (AgentCore Policy), cost and latency tracking, versioning, a
feedback loop (AgentCore Memory) and a weekly KB gap report.

> **Scope:** this project applies production-grade practices, but they are validated only on a
> simulated environment with chaos-injected failures. It has not been proven in production.

## Quick start

```bash
uv sync                      # install deps (Python 3.12)
cp .env.example .env         # fill in region / model IDs; credentials via AWS profile
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
uv run python scripts/verify_model_access.py   # checks Bedrock model access (needs AWS creds)
```

## Layout

| Dir | Purpose |
|---|---|
| `agent/` | Settings, and the Strands agent that AgentCore Runtime hosts (approval flow) |
| `tools/` | Lambda tools behind AgentCore Gateway (typed, read-only diagnostics) |
| `kb/` | Runbooks / postmortems source docs |
| `evals/` | RAGAS + custom evals, CI gate |
| `infra/` | AWS CDK (Python) |
| `observability/` | Logging, tracing, cost/latency |
| `scripts/` | Ops scripts (verify access, teardown, reports) |
| `docs/` | Docs, `PROGRESS.md` |

The project status is tracked in [docs/PROGRESS.md](docs/PROGRESS.md).
