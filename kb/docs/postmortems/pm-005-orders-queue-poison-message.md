# Postmortem: Order fulfilment delayed by a poison message in the orders queue (2026-07-21)

## Summary
A malformed order event (null `shipping_address` from a new mobile client version) made
orders-worker throw on every attempt. The queue had no dead-letter queue configured, so the message
was retried indefinitely, and a worker bug held a batch lock while retrying, blocking other
messages. Fulfilment lagged by up to 2 hours.

## Symptoms
- `ApproximateAgeOfOldestMessage` grew to 7,200 s.
- orders-worker logs repeated `NullPointerException` for the same message ID.
- Customers reported missing confirmation emails.

## Impact
- About 9,000 orders delayed; no orders lost. SEV2.

## Timeline
- 10:10 mobile app 7.4 release begins rollout.
- 10:32 first malformed event enqueued.
- 10:45 SQSQueueAgeHigh fires; treated as load at first, worker scaled out with no effect.
- 11:40 same message ID found repeating in logs.
- 12:05 message moved aside manually; queue drains by 12:50.

## Root cause
No DLQ / `maxReceiveCount`; worker retried in-process while holding the batch; mobile client sent
an unvalidated payload.

## Diagnosis steps
- Compared send vs delete rates: deletes near zero despite healthy pods.
- Grouped worker errors by message ID.

## Mitigation
- Moved the poison message aside, which unblocked the queue.

## Rollback
- Mobile release paused at 20%.

## Escalation
- Orders on-call, Mobile team.

## Action items
- Configure DLQ with `maxReceiveCount=5` on all queues.
- Validate order events at the API boundary.
- Alert on repeated failures of the same message ID.

## Related alerts
- SQSQueueAgeHigh
- SQSQueueDepthHigh
- DLQMessagesVisible
