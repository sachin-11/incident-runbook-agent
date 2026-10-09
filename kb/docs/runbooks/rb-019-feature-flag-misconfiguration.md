# Runbook: Feature flag or runtime config misconfiguration

Use this when errors start right after a feature flag change or a runtime configuration update,
with no code deploy. Flags change behaviour instantly for a percentage of users, so the error
pattern often matches the rollout percentage.

## Symptoms
- Errors or behaviour change at the exact minute of a flag change in the flag audit log.
- Error rate roughly equals the flag rollout percentage (for example 25% of checkout requests
  fail after a 25% rollout).
- Only users in a targeted segment (country, app version, beta group) are affected.
- Config parse errors: `invalid value for key`, `unknown enum value`.

## Impact
- Varies by flag. Flags on checkout or pricing paths are SEV1 candidates.

## Diagnosis steps
All steps are read-only.
1. Open the flag service audit log for the incident window: which flags changed, who changed them,
   old and new value, targeting rules.
2. Compare affected requests with flag evaluation logs (`flag_key`, `variation`).
3. Check for type mismatches: a JSON flag set to a string, a percentage given as 50 instead of 0.5.
4. Check whether a flag depends on a backend capability not deployed everywhere (flag on before
   code).

## Mitigation
- Turn the flag off or revert to the previous value. This is the fastest mitigation for flag
  incidents and is pre-approved for the flag owner and on-call.
- If the flag service itself is down, services use their last-known values; do not restart pods
  in bulk because they would lose the cache.

## Rollback
- Revert the flag change from the audit log entry; confirm error rate returns to baseline.

## Escalation
- Owner of the flag (listed in the flag service) and the owning team on-call.

## Related alerts
- FeatureFlagErrorSpike
- ConfigParseErrors
- CheckoutErrorRateHigh
