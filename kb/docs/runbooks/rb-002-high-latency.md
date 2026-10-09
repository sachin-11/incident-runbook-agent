# Runbook: High p99 latency on checkout-api

Use this when request latency rises without a large jump in errors. Requests still succeed, but
slowly. Checkout is the most latency-sensitive path: every 100 ms of p99 costs conversion.

## Symptoms
- p99 latency above 1.5 s for 5 minutes (normal p99 is about 350 ms); p50 may stay normal.
- Users report a slow "Place order" button or spinner; mobile clients time out at 10 s.
- Upstream timeouts in the gateway logs: `upstream request timeout` with 504 responses.
- Thread pool or event loop saturation metrics high; request queue time grows.

## Impact
- Slower checkout reduces conversion; above 3 s p99, abandoned carts rise sharply.
- Long requests hold DB connections longer, which can cascade into connection exhaustion.
- Severity: SEV3 if p99 under 3 s, SEV2 if over 3 s or if timeouts produce errors.

## Diagnosis steps
All steps are read-only.
1. Find which part of the request is slow. Open the latency breakdown by route and dependency in
   the tracing UI (spans for payments-svc, inventory-svc, Postgres, Redis).
2. Check whether latency is in this service or a dependency:
   - PromQL: `histogram_quantile(0.99, sum by (le, route) (rate(http_server_duration_seconds_bucket{service="checkout-api"}[5m])))`
   - Compare with client-side spans to payments-svc and inventory-svc.
3. Check saturation of the pods: CPU throttling (`container_cpu_cfs_throttled_periods_total`),
   memory, GC pause time, and request concurrency per pod.
4. Check database time: slow query log, `pg_stat_activity` for long-running queries, lock waits.
5. Check recent changes: deploys in the last 2 hours, feature flag changes, traffic spikes
   (marketing campaign, bot traffic).
6. Check cache hit ratio for the product and price cache; a cold cache multiplies DB load.

## Mitigation
- If one dependency is slow, enable its fallback or reduce its timeout so checkout fails fast and
  retries are bounded.
- If pods are CPU-throttled, scale out: raise HPA min replicas temporarily.
- If a new deploy introduced the latency (N+1 query, missing index), roll back.
- If bot traffic is the cause, apply the WAF rate-based rule for the offending source.

## Rollback
- Roll back the latest checkout-api deploy: `kubectl rollout undo deployment/checkout-api -n shop`.
- Revert any feature flag flipped in the incident window.
- Return HPA min replicas to the baseline once p99 has been normal for 30 minutes.

## Escalation
- checkout-api on-call (Payments & Checkout team).
- If the slow span is Postgres, add the DBA on-call.
- If p99 over 3 s for 15 minutes, declare SEV2 and page the incident commander.

## Related alerts
- HighP99Latency
- CheckoutLatencySLOBurn
- GatewayUpstreamTimeout
