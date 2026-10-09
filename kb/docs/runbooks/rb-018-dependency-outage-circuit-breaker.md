# Runbook: Third-party dependency outage and open circuit breaker (email provider)

Use this when notification-svc's circuit breaker to the email/SMS provider opens because the
provider is failing or slow. The breaker protects our service; the job is to confirm the outage,
keep messages safe and recover cleanly.

## Symptoms
- Circuit breaker state `OPEN` for `email-provider` in notification-svc metrics.
- Provider calls fail with timeouts or 5xx; provider status page may show an incident.
- Notification queue grows; order confirmation and password reset emails delayed.

## Impact
- Delayed emails and SMS. Password reset and 2FA codes are the most urgent: users may be locked
  out. SEV2 if 2FA SMS is affected, otherwise SEV3.

## Diagnosis steps
All steps are read-only.
1. Confirm the breaker state and failure ratio in the last 10 minutes.
2. Check the provider status page and our synthetic check that sends a test email every 5 minutes.
3. Separate provider outage from our own problem: DNS resolution, egress NAT gateway errors,
   expired API key (401), or account suspension for bounce rate.
4. Check queue depth and age of the notification queue.

## Mitigation
- Keep messages queued (do not drop). The breaker half-opens automatically and retries.
- Fail over to the secondary provider for transactional emails (flag
  `notifications.provider.failover`, needs approval because of cost).
- Prioritize 2FA and password reset messages over marketing (priority queue flag).

## Rollback
- Switch back to the primary provider after its incident is resolved and the breaker has been
  closed for 15 minutes.

## Escalation
- Notification team on-call.
- Vendor support for the provider; Identity team if 2FA is affected.

## Related alerts
- CircuitBreakerOpen
- NotificationQueueAgeHigh
- EmailProviderErrorRateHigh
