# Runbook: Auth token validation failures (401s across services)

Use this when users are logged out or API calls fail with 401 Unauthorized because tokens cannot be
validated: signing key rotation, JWKS endpoint unreachable, or clock skew.

## Symptoms
- Sudden spike of HTTP 401 across many services at once, while auth-svc login works.
- Logs: `invalid signature`, `kid not found in JWKS`, `token used before issued (nbf)`,
  `JWT expired` with fresh tokens.
- Users forced to log in again repeatedly; mobile app login loops.

## Impact
- Logged-in actions fail: checkout, order history, account. SEV1 if login or checkout is broken
  for most users.

## Diagnosis steps
All steps are read-only.
1. Check whether the signing key rotated recently (auth-svc deploy log, key management events).
2. Fetch the JWKS and compare `kid` values with the `kid` in a failing token header:
   `curl -s https://auth.internal/.well-known/jwks.json`
3. Check services' JWKS cache TTL: services caching the old key set for hours reject new tokens.
4. Check clock skew on nodes: `chronyc tracking` via the node debug tooling; skew over 60 s breaks
   `nbf`/`exp` checks.
5. Check whether JWKS endpoint is reachable from the failing services (network policy, DNS).

## Mitigation
- Publish both old and new keys in JWKS during rotation (overlap period) if the old key was
  removed too early.
- Restart services with stale JWKS caches (rolling restart).
- Fix NTP on nodes with skew; replace bad nodes.

## Rollback
- Roll back to the previous signing key if the new key is not distributed yet (Security approval).

## Escalation
- Identity team on-call (owns auth-svc).
- Security team for any key change.

## Related alerts
- AuthTokenValidationFailures
- Http401RateHigh
- NodeClockSkewHigh
