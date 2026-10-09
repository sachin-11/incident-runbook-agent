# CLAUDE.md

<!-- TODO: the original master prompt was not available when this file was created.
     Paste it here verbatim; the sections below are derived from README.md and docs/. -->

## Project

Incident Runbook Agent: an AI agent on AWS, hosted on Amazon Bedrock AgentCore. When an alert
arrives, it
1. retrieves relevant runbooks and postmortems from a Bedrock Knowledge Base and cites them,
2. runs safe, read-only diagnostics through Lambda tools behind AgentCore Gateway (logs, health,
   deploys, metrics),
3. proposes a fix and asks a human for approval before any risky action. AgentCore Policy enforces
   this at the Gateway.

The AgentOps layer covers tracing (AgentCore Observability), evals with a CI gate (RAGAS and
AgentCore Evaluations), guardrails (AgentCore Policy), cost and latency tracking, versioning, a
feedback loop (AgentCore Memory) and a weekly KB gap report.

## Platform decision (2026-10-09)

The agent layer uses **AgentCore**, not Bedrock Agents:
- **Runtime** hosts a Strands Agents (Python) agent. The framework and model are our choice.
- **Gateway** exposes the `tools/` Lambdas as MCP tools.
- **Policy** (Cedar) enforces read-only tools and blocks state-changing tools unless a matching
  approval exists. This replaces Bedrock return-of-control.
- **Memory** keeps incident history.
- **Observability** sends OTel traces to CloudWatch.
- **Evaluations** scores agent quality, alongside the RAGAS CI gate.

The Knowledge Base (Module 2) does not change. The agent reads it through a retrieve tool.
AgentCore still calls models through Bedrock, so the account's Bedrock quotas apply to it too.

Scope: production-grade practices, validated only on a simulated environment with chaos-injected
failures. Never claim it is proven in production.

## Layout

| Dir | Purpose |
|---|---|
| `agent/` | Settings, and the Strands agent that AgentCore Runtime hosts (approval flow) |
| `tools/` | Lambda tools behind AgentCore Gateway (typed, read-only diagnostics) |
| `kb/` | Runbooks / postmortems source docs |
| `evals/` | RAGAS + custom evals, CI gate |
| `infra/` | AWS CDK (Python): KnowledgeBase, Tools, Agent (AgentCore), Observability stacks |
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
