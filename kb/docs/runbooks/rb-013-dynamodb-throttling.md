# Runbook: DynamoDB throttling (inventory-svc)

Use this when DynamoDB rejects reads or writes with `ProvisionedThroughputExceededException` or
`ThrottlingException` on the inventory table.

## Symptoms
- CloudWatch `ReadThrottleEvents` / `WriteThrottleEvents` above zero; `ThrottledRequests` rising.
- inventory-svc logs `ProvisionedThroughputExceededException` and SDK retry exhaustion.
- Stock checks and reservations slow down; checkout shows "item availability unknown".
- Throttling concentrated on one partition: a hot key (a single best-selling SKU during a drop).

## Impact
- Inventory reservations fail or lag; risk of overselling or blocked checkouts.
- SEV2 during a sale event.

## Diagnosis steps
All steps are read-only.
1. Capacity mode and limits: `aws dynamodb describe-table --table-name inventory` (on-demand or
   provisioned, autoscaling settings, GSIs).
2. Compare `ConsumedWriteCapacityUnits` with provisioned capacity; check whether autoscaling is
   lagging behind a sudden spike (it reacts in minutes).
3. Check GSI throttling: a throttled GSI back-pressures writes on the base table.
4. Find hot partitions with CloudWatch Contributor Insights for the table (top partition keys).
5. Check for a scan or batch job (stock sync, nightly export) consuming capacity.

## Mitigation
- Provisioned mode: raise capacity or switch the table to on-demand (needs approval; on-demand
  switch is allowed once per 24 hours).
- Pause the batch job that consumes capacity.
- For a single hot SKU, enable the write-sharding flag for reservations
  (`inventory.reservation.sharded`).

## Rollback
- Return to the previous capacity mode after the event if cost matters, respecting the 24-hour
  switch limit.

## Escalation
- Inventory team on-call.
- AWS support if throttling occurs below provisioned capacity (possible partition issue).

## Related alerts
- DynamoDBThrottledRequests
- DynamoDBWriteThrottleEvents
- InventoryReservationLatencyHigh
