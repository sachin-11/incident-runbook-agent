# Runbook: Database connection pool exhaustion (Postgres orders-db)

Use this when services cannot get a database connection. The app-side pool is empty or Postgres
has reached `max_connections`. Requests wait for a connection, then time out.

## Symptoms
- Errors in app logs: `HikariPool-1 - Connection is not available, request timed out after 30000ms`
  or `FATAL: sorry, too many clients already` or `remaining connection slots are reserved`.
- Pool metrics: active connections equal max pool size, pending threads above zero.
- `numbackends` on orders-db close to `max_connections` (500).
- Latency climbs first, then 5xx errors appear on checkout-api and orders-worker.

## Impact
- Every service sharing orders-db is affected: checkout, order history, the orders-worker.
- Writes fail, so orders cannot be placed. Usually SEV1 if checkout errors exceed 5%.

## Diagnosis steps
All steps are read-only.
1. Count connections by application and state:
   `SELECT application_name, state, count(*) FROM pg_stat_activity GROUP BY 1,2 ORDER BY 3 DESC;`
2. Look for `idle in transaction` sessions; they hold connections and locks. Note their age:
   `SELECT pid, application_name, now() - xact_start AS age, query FROM pg_stat_activity WHERE state = 'idle in transaction' ORDER BY age DESC LIMIT 20;`
3. Check total pool demand: replicas x pool size per pod. A scale-out (HPA added pods) can push
   the total over `max_connections` even though each pod's pool is unchanged.
4. Check for slow queries holding connections: long `active` sessions and lock waits.
5. Check recent deploys that changed pool size, transaction scope, or added a new query path.
6. Check RDS Proxy (if used) metrics: `DatabaseConnectionsCurrentlyBorrowed`, `ClientConnections`.

## Mitigation
- Reduce demand: scale down non-critical consumers (reporting jobs, batch exports) first.
- If an app leaks connections or holds idle-in-transaction sessions, restart its pods one at a
  time; this returns connections to Postgres.
- Terminating a specific runaway session (`pg_terminate_backend(pid)`) is a write action: it needs
  approval from the DBA on-call.
- Cap HPA max replicas temporarily so total pool demand fits `max_connections`.

## Rollback
- Roll back the deploy that changed pool size or transaction handling.
- Undo temporary HPA caps and scaled-down jobs once connection count is below 70% for 30 minutes.

## Escalation
- DBA on-call immediately for SEV1.
- Owning team of the application with the most connections.
- If RDS itself is unhealthy (failover, storage), open an AWS support case (Business, urgent).

## Related alerts
- DBConnectionPoolExhausted
- PostgresTooManyConnections
- HikariPendingThreadsHigh
