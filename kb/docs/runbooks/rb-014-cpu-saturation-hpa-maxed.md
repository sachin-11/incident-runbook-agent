# Runbook: CPU saturation with HPA at max replicas (search-svc)

Use this when a service is CPU-bound and the Horizontal Pod Autoscaler cannot add more pods because
it has reached `maxReplicas`, or new pods stay Pending because the cluster has no room.

## Symptoms
- HPA status shows current replicas equal to max; target CPU utilization above 100% of request.
- CPU throttling: `container_cpu_cfs_throttled_periods_total` rate high.
- New pods `Pending` with event `0/12 nodes are available: Insufficient cpu`.
- Search latency rises, results time out, autocomplete feels laggy.

## Impact
- Degraded search and browse; slower product discovery reduces conversion. SEV3, SEV2 if search
  errors exceed 5%.

## Diagnosis steps
All steps are read-only.
1. `kubectl get hpa search-svc -n shop` and `kubectl describe hpa search-svc -n shop`.
2. Check Pending pods and why: `kubectl get pods -n shop --field-selector=status.phase=Pending`.
3. Check cluster autoscaler or Karpenter logs: is it adding nodes, or blocked by instance limits,
   subnet IP exhaustion, or EC2 capacity in the AZ?
4. Is load real? Compare RPS with last week; check for bot scraping or an expensive new query type.
5. Profile per-request CPU: did a deploy make each query more expensive (new ranking model, regex)?

## Mitigation
- Raise HPA `maxReplicas` temporarily if nodes are available (needs approval).
- If nodes are not available, check autoscaler limits and EC2 quotas; request quota increase.
- Block or rate-limit scraping traffic at the WAF.
- Turn off expensive optional features (fuzzy search, personalized ranking) via flags.

## Rollback
- Return HPA max to the baseline after load drops; re-enable optional features one at a time.

## Escalation
- Search team on-call.
- Platform team for node capacity and autoscaler problems.

## Related alerts
- HPAMaxReplicas
- CPUThrottlingHigh
- KubePodsPendingInsufficientCPU
