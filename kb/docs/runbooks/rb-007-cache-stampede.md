# Runbook: Cache stampede (thundering herd on Redis miss)

Use this when many requests miss the cache at the same moment and all hit the database to rebuild
the same keys. Common triggers: Redis failover or flush, a popular key expiring, or a deploy that
changes the cache key format.

## Symptoms
- Cache hit ratio drops suddenly (for example from 95% to 20%) for catalog or price keys.
- Database CPU and QPS jump at the same instant; identical queries dominate `pg_stat_statements`.
- Redis CPU spikes or Redis shows many concurrent `SET` for the same key.
- catalog-api latency rises sharply, then recovers once the cache warms, unless the DB tips over first.

## Impact
- Product pages slow down or fail; checkout price lookups may time out.
- Can cascade into database connection exhaustion.
- Severity: SEV2 if the database saturates.

## Diagnosis steps
All steps are read-only.
1. Confirm the hit ratio drop: `rate(cache_hits_total[1m]) / rate(cache_requests_total[1m])` by
   service.
2. Check Redis events in the same minute: ElastiCache events for failover, node replacement, or
   a `FLUSHALL` in the slow log/audit log.
3. Check if a deploy changed the cache key prefix or serialization version (all keys miss at once).
4. Find hot keys: top queries in `pg_stat_statements` by calls in the last 10 minutes; they map to
   the keys being rebuilt.
5. Check TTLs: many keys created at the same time with the same TTL expire together.

## Mitigation
- Enable request coalescing (single-flight) for cache rebuilds if the feature flag exists
  (`catalog.cache.singleflight`).
- Serve stale values while rebuilding (stale-while-revalidate flag).
- Temporarily rate-limit the most expensive uncached endpoint at the gateway.
- Pre-warm the top 1,000 product keys with the warm-up job (needs approval; it adds load).

## Rollback
- If a deploy changed key format, roll it back so old keys hit again.
- Turn off temporary rate limits once hit ratio is back above 90%.

## Escalation
- Catalog team on-call.
- Platform/Redis owners if the trigger was a failover or node problem.
- DBA on-call if Postgres CPU stays above 90%.

## Related alerts
- CacheHitRatioDrop
- RedisCPUHigh
- PostgresCPUHigh
