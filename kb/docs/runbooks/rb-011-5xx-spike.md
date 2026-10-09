# Runbook: 5xx error spike at the edge (ALB / API gateway)

Use this when the load balancer or API gateway reports a sudden rise in 5xx responses and the
source service is not yet known. This runbook is about locating the origin quickly.

## Symptoms
- ALB `HTTPCode_Target_5XX_Count` or `HTTPCode_ELB_5XX_Count` jumps; error rate above 2% for 5 min.
- Status code mix tells the story: 502 (bad gateway, target closed connection), 503 (no healthy
  targets), 504 (target timeout), 500 (application error).
- Customer-facing error pages; synthetic checks fail.

## Impact
- Direct customer impact on whatever routes are failing. SEV1 if checkout or login error rate is
  above 5%, otherwise SEV2.

## Diagnosis steps
All steps are read-only.
1. Split by code and source: `HTTPCode_ELB_5XX` means the load balancer generated the error (no
   healthy target, connection failure); `HTTPCode_Target_5XX` means the service returned it.
2. Split by target group / route to find the failing service. In gateway logs group by
   `upstream_service` and `status`.
3. For 503 from the ELB: check target group healthy host count. Zero healthy targets means pods
   failed health checks (see the crashloop runbook) or were deregistered.
4. For 502: check for pods being killed mid-request (OOM, deploys without proper
   `preStop` / connection draining), or keep-alive timeout mismatch (target idle timeout shorter
   than the ALB's 60 s).
5. For 504: the target is too slow; follow the high latency runbook for that service.
6. Correlate with deploys, feature flags, and dependency status in the same minute.

## Mitigation
- Roll back the deploy that coincides with the spike.
- If one AZ is unhealthy, shift traffic away from it (zonal shift; needs approval).
- If 502s come from connection reuse, raise the service's keep-alive timeout above the ALB idle timeout.

## Rollback
- Roll back the affected service; re-enable the AZ after the AWS Health event clears.

## Escalation
- Owning team of the failing service once identified.
- Platform team for ALB, ingress and zonal shift.
- Incident commander if more than one tier-1 service is failing.

## Related alerts
- ALB5xxSpike
- GatewayErrorRateHigh
- TargetGroupUnhealthyHosts
