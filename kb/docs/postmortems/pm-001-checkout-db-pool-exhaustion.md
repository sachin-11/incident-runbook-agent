# Postmortem: Checkout outage from orders-db connection exhaustion (2026-03-14)

## Summary
A checkout-api release raised the per-pod connection pool from 20 to 50. During the evening peak
the HPA scaled checkout-api to 14 pods, so total demand reached 700 connections against a Postgres
`max_connections` of 500. Checkout failed for 38 minutes.

## Symptoms
- `FATAL: sorry, too many clients already` from checkout-api and orders-worker.
- `HikariPool-1 - Connection is not available, request timed out after 30000ms`.
- Checkout 5xx rate reached 41%; p99 latency 30 s (pool wait timeout).

## Impact
- 38 minutes of degraded checkout, about 2,100 failed orders, estimated revenue loss significant.
- orders-worker also failed to connect, delaying fulfilment by about 1 hour. Declared SEV1.

## Timeline
- 18:05 release 4.12.0 of checkout-api deployed (pool size change bundled with a refactor).
- 19:40 traffic peak; HPA scales checkout-api from 6 to 14 pods.
- 19:42 DBConnectionPoolExhausted and PostgresTooManyConnections fire.
- 19:50 incident declared SEV1; DBA joins.
- 20:05 root cause identified from `pg_stat_activity` grouped by application.
- 20:12 rollback of checkout-api to 4.11.3; HPA max temporarily capped at 8.
- 20:20 error rate back to baseline.

## Root cause
Pool size per pod was changed without multiplying by maximum replicas. No guardrail checked
`max_replicas x pool_size` against the database limit.

## Diagnosis steps
- Grouped `pg_stat_activity` by `application_name`: checkout-api held 650 of 500+ slots.
- Compared Helm values between releases: `DB_POOL_MAX` 20 -> 50.

## Mitigation
- Capped HPA max replicas and rolled back the release.

## Rollback
- Rolled back to 4.11.3; HPA cap removed the next morning after the pool fix.

## Escalation
- Paged checkout on-call, DBA on-call, incident commander.

## Action items
- Add a CI check: sum over services of `max_replicas x pool_size` must stay below 80% of
  `max_connections`.
- Introduce RDS Proxy for checkout-api and orders-worker.
- Alert on connection count above 70% of max.

## Related alerts
- DBConnectionPoolExhausted
- PostgresTooManyConnections
- CheckoutErrorRateHigh
