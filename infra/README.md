# infra/

AWS CDK app (Python). Four stacks, prefixed by stage (`Ira-<stage>-...`):

| Stack | Holds |
|---|---|
| `KnowledgeBaseStack` | KB, S3 source bucket, vector store |
| `ToolsStack` | Diagnostic Lambdas |
| `AgentStack` | Bedrock Agent, alias, action groups, guardrails |
| `ObservabilityStack` | Dashboards, alarms, cost and latency |

```bash
cd infra && npx aws-cdk@2 synth          # or: make synth
npx aws-cdk@2 synth -c stage=prod         # stage also reads IRA_STAGE
```

Synth needs Node but no AWS credentials. Status: all stacks are empty.
