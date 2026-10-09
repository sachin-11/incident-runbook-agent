# Runbook: Bad deploy (error or latency regression right after a release)

Use this when a metric regresses within about 30 minutes of a deploy and no other change explains
it. The default response is to roll back first and investigate after.

## Symptoms
- Error rate or latency changes in step with the deploy marker on the dashboard.
- Only pods running the new version show the errors (compare by `version` label).
- Canary analysis fails or the progressive rollout pauses automatically.
- New exception types appear in logs that did not exist before the release.

## Impact
- Depends on the change and how far the rollout got. A canary at 10% limits blast radius;
  a full rollout affects all traffic.
- Severity follows the impacted metric: SEV2 for a broad error regression on a tier-1 service.

## Diagnosis steps
All steps are read-only.
1. Confirm timing: list deploys in the window from the CI/CD history and the deploy annotations on
   the dashboard.
2. Split metrics by version: PromQL
   `sum by (version) (rate(http_requests_total{service="<svc>",code=~"5.."}[5m]))`
3. Diff the release: `git log <prev_tag>..<new_tag> --oneline` and the config diff (env vars,
   feature flags, Helm values).
4. Check for schema migrations shipped with the release; they decide whether rollback is safe.
5. Look at the new exception types in logs, grouped by message.

## Mitigation
- Stop the rollout if it is still progressing: `kubectl rollout pause deployment/<svc> -n <ns>`
  or pause the pipeline stage.
- Roll back (see below) unless the release contains a non-backward-compatible migration.
- If rollback is unsafe, disable the new code path with its feature flag.

## Rollback
- Kubernetes: `kubectl rollout undo deployment/<svc> -n <ns>` or redeploy the previous tag from the
  pipeline (preferred, so the pipeline state matches reality).
- Verify error rate and latency return to the pre-deploy baseline within 10 minutes.
- Block the bad version in the pipeline. Write down the migration state if one ran.

## Escalation
- Author of the change and the owning team on-call.
- Release manager if the rollout is part of a coordinated multi-service release.

## Related alerts
- DeployErrorRateRegression
- CanaryAnalysisFailed
- KubeDeploymentRolloutStuck
