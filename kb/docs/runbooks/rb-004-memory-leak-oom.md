# Runbook: Memory leak and OOMKilled containers (catalog-api)

Use this when container memory grows steadily until the kernel OOM killer terminates it (exit code
137, reason `OOMKilled`), or when JVM/Node heap usage only ever goes up between deploys.

## Symptoms
- Memory graph is a sawtooth: climbs over hours, drops to zero at each restart.
- `kubectl describe pod` shows `Last State: Terminated, Reason: OOMKilled, Exit Code: 137`.
- GC time rises as heap fills; latency gets worse shortly before each kill.
- `java.lang.OutOfMemoryError: Java heap space` or `FATAL ERROR: Reached heap limit` (Node) in logs.

## Impact
- Each OOM kill drops in-flight requests on that pod (502/503 at the gateway).
- If all pods leak at the same rate they die together, causing a short full outage.
- Severity: SEV3 if restarts are spread out, SEV2 if several pods die at once.

## Diagnosis steps
All steps are read-only.
1. Confirm OOM is the cause: `kubectl get pods -n shop -l app=catalog-api` then
   `kubectl describe pod <pod>` and look for `OOMKilled`.
2. Compare memory growth rate before and after the last deploy:
   PromQL `container_memory_working_set_bytes{container="catalog-api"}` over 24 hours.
3. Check the container limit vs the runtime heap setting. JVM `-Xmx` near the container limit
   leaves no room for metaspace, threads and direct buffers.
4. Look for unbounded caches or collections: in-process caches without max size or TTL, request
   context stored in global maps, listeners that are never removed.
5. Pull a heap dump from one pod (read-only for the service, but it pauses the JVM; do it on a
   pod already drained from the load balancer).
6. Check whether traffic shape changed: a larger catalog page size or a new endpoint returning
   big payloads can look like a leak.

## Mitigation
- Short term: raise the memory limit by 25 to 50% to stretch time between kills, and keep enough
  replicas that rolling kills do not overlap.
- If the leak arrived with a deploy, roll back.
- Schedule a rolling restart every few hours as a stopgap while the fix is built (document it as
  temporary).

## Rollback
- `kubectl rollout undo deployment/catalog-api -n shop`
- Revert the memory limit change once the fix ships; a permanently higher limit hides the next leak.

## Escalation
- Catalog team on-call.
- Platform team if OOMs are node-level (node `MemoryPressure`, system pods killed).

## Related alerts
- ContainerOOMKilled
- ContainerMemoryNearLimit
- JvmGcTimeHigh
