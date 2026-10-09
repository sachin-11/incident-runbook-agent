# Postmortem: Catalog slowdown after Redis failover caused cache stampede (2026-04-02)

## Summary
A planned ElastiCache maintenance triggered a primary failover. The new primary started with an
empty cache. Thousands of catalog-api requests missed at once and rebuilt the same product keys
from Postgres, pushing database CPU to 100% for 22 minutes.

## Symptoms
- Cache hit ratio fell from 96% to 8% within one minute.
- Postgres CPU 100%, the same product query making up 70% of calls.
- Product page p99 latency 9 s; some 504s at the gateway.

## Impact
- 22 minutes of slow or failing product pages; checkout price lookups slowed. Declared SEV2.

## Timeline
- 03:00 ElastiCache maintenance window starts; failover at 03:04.
- 03:05 CacheHitRatioDrop and PostgresCPUHigh fire.
- 03:12 on-call identifies identical queries in `pg_stat_statements`.
- 03:15 stale-while-revalidate flag enabled; gateway rate limit on product listing endpoint.
- 03:27 hit ratio back above 90%; limits removed at 03:45.

## Root cause
No request coalescing for cache rebuilds, and replication to the replica was not preserving data
because the cluster used a single node per shard. Failover therefore meant a cold cache.

## Diagnosis steps
- Correlated the hit-ratio drop with the ElastiCache failover event.
- Found hot queries via `pg_stat_statements` sorted by calls.

## Mitigation
- Enabled stale-while-revalidate and a temporary gateway rate limit.

## Rollback
- Removed the rate limit after recovery; flag kept on permanently.

## Escalation
- Catalog on-call and Platform (Redis owners).

## Action items
- Implement single-flight cache rebuilds in catalog-api.
- Add a replica per shard so failover keeps the warm dataset.
- Add jitter to TTLs.

## Related alerts
- CacheHitRatioDrop
- PostgresCPUHigh
- RedisCPUHigh
