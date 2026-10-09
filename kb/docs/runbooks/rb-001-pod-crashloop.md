# Runbook: Pods in CrashLoopBackOff (container keeps restarting)

Use this when Kubernetes pods restart repeatedly, often right after a deploy or a config/secret
change. The container starts, exits (non-zero code, failed probe, or OOM), and the kubelet backs
off with growing delays (10s, 20s, 40s ... up to 5 minutes).

## Symptoms
- `kubectl get pods` shows `CrashLoopBackOff` or `Error` status and a RESTARTS count that keeps
  climbing (for example 7 restarts in 10 minutes).
- Pods restarting repeatedly after a deploy: the new ReplicaSet never becomes Ready, so the rollout
  stalls at "Waiting for deployment rollout to finish: 1 of 3 updated replicas are available".
- Container `Last State: Terminated` with `Exit Code: 1` (app error), `137` (SIGKILL, often OOM or
  failed liveness probe) or `143` (SIGTERM).
- Readiness probe failures in events: `Readiness probe failed: HTTP probe failed with statuscode: 503`.
- Service capacity drops; the remaining old pods take all traffic and latency rises.

## Impact
- If all replicas crash, the service is fully down (5xx from the gateway, empty endpoints).
- During a stalled rollout the old ReplicaSet usually keeps serving, so impact is reduced capacity
  rather than an outage. Check `maxUnavailable` on the Deployment.
- Severity: SEV2 if partial capacity loss, SEV1 if the Service has zero ready endpoints.

## Diagnosis steps
All steps are read-only.
1. List affected pods and restart counts:
   `kubectl get pods -n <ns> -l app=<service> -o wide`
2. Read the termination reason and exit code:
   `kubectl describe pod <pod> -n <ns>` and look at `Last State`, `Reason`, `Exit Code`, and the
   Events section (probe failures, `Back-off restarting failed container`).
3. Read logs from the previous (crashed) container, not the current one:
   `kubectl logs <pod> -n <ns> --previous --tail=200`
   Typical causes: missing environment variable, secret not mounted, config parse error,
   cannot connect to database on startup, port already in use, migration failure.
4. Check whether a deploy just happened:
   `kubectl rollout history deployment/<service> -n <ns>` and compare the image tag and config
   hash with the previous revision. Check the deploy log in the CI/CD tool.
5. If exit code is 137 and reason is `OOMKilled`, follow the memory leak / OOM runbook instead.
6. If the reason is a failing liveness probe, compare probe `initialDelaySeconds` with real startup
   time. Slow startup after a dependency upgrade often trips the probe.
7. Confirm that ConfigMaps and Secrets referenced by the pod exist:
   `kubectl get configmap,secret -n <ns>`

## Mitigation
- If the crash started with a deploy: roll back first, debug later (see Rollback).
- If a Secret or ConfigMap key is missing or renamed, restore the expected key and restart the
  rollout. Do not edit Secrets by hand in prod without a change ticket.
- If a liveness probe kills a slow-starting container, add or increase a `startupProbe` instead of
  disabling the liveness probe.
- If a dependency (DB, cache) is unreachable at startup, fix the dependency; the pods recover on
  their own once it is healthy. Consider making startup tolerant of dependency delays.

## Rollback
- `kubectl rollout undo deployment/<service> -n <ns>` returns to the previous ReplicaSet.
- Verify: `kubectl rollout status deployment/<service> -n <ns>` and confirm RESTARTS stops
  increasing and the error rate returns to baseline.
- Mark the bad image tag as blocked in the deploy pipeline so it is not promoted again.

## Escalation
- Owning service team on-call first (from the service catalog).
- If more than one service is crashlooping at the same time, page the Platform team: it may be a
  node, CNI, or cluster-wide config issue.
- Escalate to SEV1 incident commander if zero endpoints for more than 5 minutes.

## Related alerts
- KubePodCrashLooping
- KubeDeploymentReplicasMismatch
- KubeDeploymentRolloutStuck
