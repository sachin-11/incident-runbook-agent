# infra/

AWS CDK app (Python). Four stacks, prefixed by stage (`Ira-<stage>-...`):

| Stack | Holds |
|---|---|
| `KnowledgeBaseStack` | Bedrock KB, S3 docs bucket, S3 Vectors index (deployed) |
| `ToolsStack` | Diagnostic Lambdas |
| `AgentStack` | AgentCore Runtime, Gateway (Lambda targets), Policy, Memory |
| `ObservabilityStack` | AgentCore Observability, dashboards, alarms, cost and latency |

```bash
cd infra && npx aws-cdk@2 synth          # or: make synth
npx aws-cdk@2 synth -c stage=prod         # stage also reads IRA_STAGE
```

Synth needs Node but no AWS credentials. Status: `KnowledgeBaseStack` is implemented; the
others are empty.
