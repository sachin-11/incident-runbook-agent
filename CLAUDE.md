# CLAUDE.md

<!-- TODO: the original master prompt was not available when this file was created.
     Paste it here verbatim; the sections below are derived from README.md and docs/. -->

## Project

Incident Runbook Agent: an AI agent on AWS (Amazon Bedrock) that, when an alert arrives,
1. retrieves relevant runbooks and postmortems from a Bedrock Knowledge Base and cites them,
2. runs safe, read-only diagnostics through action-group Lambdas (logs, health, deploys, metrics),
3. proposes a fix and asks a human for approval (return of control) before any risky action.

The AgentOps layer covers tracing, evals with a CI gate, guardrails, cost and latency tracking,
versioning, a feedback loop and a weekly KB gap report.

Scope: production-grade practices, validated only on a simulated environment with chaos-injected
failures. Never claim it is proven in production.

## Layout

| Dir | Purpose |
|---|---|
| `agent/` | Agent config, orchestration, return-of-control handling |
| `tools/` | Action-group Lambdas (typed, read-only diagnostics) |
| `kb/` | Runbooks / postmortems source docs |
| `evals/` | RAGAS + custom evals, CI gate |
| `infra/` | AWS CDK (Python): KnowledgeBase, Tools, Agent, Observability stacks |
| `observability/` | Logging, tracing, cost/latency |
| `scripts/` | Ops scripts (verify access, teardown, reports) |
| `tests/` | Unit tests |
| `docs/` | `PROGRESS.md`, `ARCHITECTURE.md` |

## Working rules

- Work one module at a time. Finish it, run the acceptance checks, update `docs/PROGRESS.md`
  (and `docs/ARCHITECTURE.md`), then stop. Do not start the next module unasked.
- No credentials in code or `.env`; use the AWS profile. Region and model IDs come from `IRA_*`
  env vars and have no defaults in code.
- Diagnostic tools are read-only. Any state-changing action needs human approval.
- Every Lambda and agent step logs via `observability.logging` inside `log_context()`.
- Keep costs low: prefer local simulation, tear down what you deploy, respect the budget caps.

## Commands

```bash
make install     # uv sync --locked + pre-commit hooks
make check       # lint + typecheck + test (what CI runs)
make format
make synth       # cd infra && npx aws-cdk@2 synth (Node, no AWS creds)
make precommit   # pre-commit run --all-files
```

Windows: `make` comes from `winget install ezwinports.make`.
