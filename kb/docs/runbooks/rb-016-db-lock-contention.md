# Runbook: Database lock contention and slow queries

Use this when queries on orders-db wait on locks or a single query becomes slow and blocks others.
Typical triggers: a migration taking an `ACCESS EXCLUSIVE` lock, a long transaction, or a missing
index after a schema change.

## Symptoms
- `pg_stat_activity` shows many sessions with `wait_event_type = 'Lock'`.
- Deadlock errors: `ERROR: deadlock detected`.
- `lock_timeout` or `statement_timeout` errors in app logs: `canceling statement due to lock timeout`.
- One query with mean time jumping in `pg_stat_statements` (for example from 2 ms to 900 ms).

## Impact
- Requests touching the locked table hang; can lead to connection exhaustion. SEV2, SEV1 if orders
  table writes are blocked.

## Diagnosis steps
All steps are read-only.
1. Find blockers and the sessions they block:
   `SELECT blocked.pid, blocked.query, blocking.pid AS blocking_pid, blocking.query AS blocking_query FROM pg_stat_activity blocked JOIN pg_stat_activity blocking ON blocking.pid = ANY(pg_blocking_pids(blocked.pid));`
2. Check whether a migration is running (schema_migrations table, deploy log). `ALTER TABLE` without
   `CONCURRENTLY` on a large table blocks all writes.
3. For a slow query, run `EXPLAIN` (not `EXPLAIN ANALYZE` on writes) and check for sequential scans
   on large tables.
4. Check autovacuum: dead tuples and table bloat on hot tables slow scans.

## Mitigation
- Cancel the blocking migration or long transaction (`pg_cancel_backend`, needs DBA approval).
- Re-run the migration later with a safe pattern (`CREATE INDEX CONCURRENTLY`, batched backfills,
  short `lock_timeout`).
- Add a missing index concurrently (approval needed).

## Rollback
- Revert the application change that introduced the slow query.
- Migration rollback only if the down-migration is tested and safe.

## Escalation
- DBA on-call.
- Author of the migration or query change.

## Related alerts
- DBLockWaitHigh
- PostgresDeadlocksDetected
- SlowQueryP95High
