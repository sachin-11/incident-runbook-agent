# Runbook: SQS queue backlog (orders-worker falling behind)

Use this when messages pile up in the orders queue faster than orders-worker consumes them. Orders
are accepted but confirmation emails, inventory reservation and fulfilment are delayed.

## Symptoms
- `ApproximateAgeOfOldestMessage` above 5 minutes (normal is under 30 s).
- `ApproximateNumberOfMessagesVisible` rising steadily.
- Dead-letter queue receiving messages; the same message IDs retried many times.
- Customers report "order placed but no confirmation email".

## Impact
- Fulfilment delays; inventory reservation lag can cause overselling.
- No direct checkout errors, so it is easy to miss; SEV2 if oldest message age exceeds 30 minutes.

## Diagnosis steps
All steps are read-only.
1. Queue depth and age:
   `aws sqs get-queue-attributes --queue-url <url> --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible ApproximateAgeOfOldestMessage`
2. Compare incoming rate (`NumberOfMessagesSent`) with consumption (`NumberOfMessagesDeleted`).
   Did input spike (sale event) or did consumption drop?
3. Check orders-worker replicas and errors: are pods crashing, or processing but failing?
4. Look for a poison message: one message that always fails and is retried until
   `maxReceiveCount`. Check the DLQ for its body (read-only peek).
5. Check downstream dependencies of the worker: inventory-svc, notification-svc, DB latency.
   A slow dependency lowers throughput per worker.
6. Check visibility timeout vs processing time; if processing takes longer than the timeout,
   messages are processed twice.

## Mitigation
- If input spiked and the worker is healthy, scale orders-worker (raise HPA max or KEDA max).
- If a poison message blocks progress, let it move to the DLQ (do not delete) and alert the owning
  team.
- If a dependency is slow, reduce worker concurrency to avoid overwhelming it, and fix the dependency.

## Rollback
- Roll back a recent orders-worker deploy if consumption dropped after it.
- Redrive DLQ messages to the main queue only after the fix ships (write action, needs approval).

## Escalation
- Orders team on-call.
- Notification team if the slow dependency is the email provider.

## Related alerts
- SQSQueueAgeHigh
- SQSQueueDepthHigh
- DLQMessagesVisible
