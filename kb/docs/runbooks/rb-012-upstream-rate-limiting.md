# Runbook: Third-party API rate limiting (payment provider returns 429)

Use this when payments-svc is throttled by the external payment provider: HTTP 429 Too Many
Requests or provider-specific `rate_limit_exceeded` errors.

## Symptoms
- payments-svc logs `429 Too Many Requests` with a `Retry-After` header from the provider.
- Payment authorization success rate drops while the provider status page is green.
- Retries multiply outbound calls: outbound RPS is higher than incoming checkout RPS.
- Checkout shows "Payment could not be processed, try again".

## Impact
- Lost or delayed orders during peak sales. SEV1 if authorization failure rate exceeds 5%.

## Diagnosis steps
All steps are read-only.
1. Measure outbound request rate to the provider and compare with the contracted limit
   (100 requests per second per merchant account).
2. Check retry behaviour: count retries per request. Retries without backoff and jitter turn a
   short throttle into a long one.
3. Check whether a batch job (refund reconciliation, card updater) is sharing the same API key and
   consuming the quota.
4. Check if traffic increased (sale, bot card-testing attack). Card-testing shows many small
   authorizations with high decline rates from few IPs.
5. Read the provider's response headers for remaining quota (`X-RateLimit-Remaining`).

## Mitigation
- Pause non-urgent batch jobs that use the same credentials.
- Enable client-side rate limiting and exponential backoff with jitter (flag
  `payments.outbound.ratelimit`).
- If card-testing is suspected, enable the WAF bot rule and CAPTCHA on checkout (Security approval).
- Ask the provider for a temporary limit increase via the support channel.

## Rollback
- Resume batch jobs once throttling has stopped for 30 minutes, ideally off-peak.
- Remove temporary WAF rules after the attack ends.

## Escalation
- Payments team on-call.
- Security team for suspected fraud or card testing.
- Provider support (priority line in the vendor contacts page).

## Related alerts
- UpstreamThrottling
- PaymentAuthFailureRateHigh
- OutboundRetryRateHigh
