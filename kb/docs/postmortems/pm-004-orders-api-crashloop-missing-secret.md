# Postmortem: orders-api pods crashlooping after deploy due to renamed secret (2026-06-08)

## Summary
A refactor renamed the environment variable `ORDERS_DB_URL` to `DATABASE_URL`, but the Kubernetes
Secret still had the old key. New pods exited on startup with a config error and restarted
repeatedly. The rollout stalled; old pods kept serving at reduced capacity until a rollback.

## Symptoms
- After the deploy, new pods restarting repeatedly: `CrashLoopBackOff`, RESTARTS rising every minute.
- `kubectl logs --previous` showed `ConfigError: required setting DATABASE_URL is missing`, exit code 1.
- Rollout stuck: "1 of 4 updated replicas are available".
- Latency up 3x on remaining old pods.

## Impact
- 25 minutes of reduced capacity and elevated latency on order APIs. Declared SEV2.

## Timeline
- 14:02 deploy of orders-api 2.30.0 starts.
- 14:05 KubePodCrashLooping fires for the new ReplicaSet.
- 14:09 KubeDeploymentRolloutStuck fires.
- 14:15 previous-container logs show the missing env var.
- 14:20 `kubectl rollout undo`; recovery by 14:27.

## Root cause
Config key rename shipped without the matching Secret change; no startup config check in CI.

## Diagnosis steps
- `kubectl describe pod` (exit code 1, Back-off restarting) and `kubectl logs --previous`.
- Diffed Helm values and the Secret's keys.

## Mitigation
- Rolled back the deployment.

## Rollback
- `kubectl rollout undo deployment/orders-api -n shop`.

## Escalation
- Orders team on-call.

## Action items
- CI step that renders manifests and validates every required env var exists in the referenced
  Secret/ConfigMap.
- Support both names for one release when renaming config keys.

## Related alerts
- KubePodCrashLooping
- KubeDeploymentRolloutStuck
- KubeDeploymentReplicasMismatch
