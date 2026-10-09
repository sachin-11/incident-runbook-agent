# Runbook: Postgres read replica lag

Use this when the read replica of orders-db falls behind the primary. Reads from the replica return
stale data: customers place an order and then do not see it in "My orders".

## Symptoms
- `ReplicaLag` CloudWatch metric above 30 s (normal under 1 s).
- Customer reports: "order confirmation shown but order missing in history".
- On the replica, `now() - pg_last_xact_replay_timestamp()` keeps increasing.
- Replica logs `canceling statement due to conflict with recovery`.

## Impact
- Stale reads for order history and admin reporting. Writes are not affected.
- SEV3 normally; SEV2 if lag exceeds 10 minutes or customer support volume rises.

## Diagnosis steps
All steps are read-only.
1. Check lag trend and when it started; correlate with heavy write events (bulk import, migration,
   `VACUUM FULL`, index build) on the primary.
2. Check replica resource saturation: CPU, IOPS, `ReadIOPS` vs provisioned, instance size smaller
   than primary.
3. Long-running queries on the replica can delay replay when `hot_standby_feedback` or
   `max_standby_streaming_delay` is configured to wait.
4. Check `WriteThroughput` on the primary: a large backfill produces WAL faster than the replica
   can apply.

## Mitigation
- Route lag-sensitive reads (order history right after checkout) to the primary via the
  `orders.read_your_writes` flag.
- Pause the bulk job on the primary until the replica catches up.
- Cancel long reporting queries on the replica (needs DBA approval).

## Rollback
- Turn off the read-your-writes flag once lag is under 1 s for 30 minutes; it adds primary load.

## Escalation
- DBA on-call.
- Orders team for the read routing flag.

## Related alerts
- ReplicaLagHigh
- PostgresReplayDelayHigh
- RDSReadReplicaLag
