# Postmortem: Expired internal mTLS certificate broke checkout to payments (2026-05-19)

## Summary
The client certificate checkout-api uses to call payments-svc over mTLS expired at 09:00 UTC.
cert-manager had failed to renew it for 3 weeks because the Issuer's credentials were rotated and
never updated. All payment calls failed for 47 minutes.

## Symptoms
- payments calls failed with `x509: certificate has expired or is not yet valid`.
- Checkout error rate 100% at payment step; no deploy in the window.
- `CertManagerCertificateNotReady` had been firing for 21 days at warning level, routed to a
  low-priority channel.

## Impact
- 47 minutes with no successful payments. SEV1.

## Timeline
- 2026-04-28 Issuer credentials rotated; renewals start failing silently.
- 09:00 certificate expires; checkout payment step fails.
- 09:03 PaymentAuthFailureRateHigh fires; SEV1 declared at 09:08.
- 09:30 `openssl s_client` shows expired client certificate.
- 09:41 Issuer credentials fixed; renewal triggered.
- 09:47 rolling restart of checkout-api picks up new certificate; recovery.

## Root cause
Renewal failure alert routed to a non-paging channel; services load the certificate only at
startup, so even a renewed certificate needs a restart.

## Diagnosis steps
- Checked served certificate dates with `openssl s_client`.
- `kubectl describe certificate` showed the renewal error from the Issuer.

## Mitigation
- Fixed Issuer credentials, renewed, rolling restart.

## Rollback
- Nothing to roll back: no change caused the outage. The fix (new certificate) stayed.

## Escalation
- Payments on-call, Platform on-call, Security.

## Action items
- Page on TLSCertExpiringSoon at 7 days for any production certificate.
- Reload certificates on file change instead of only at startup.

## Related alerts
- TLSCertExpired
- CertManagerCertificateNotReady
- PaymentAuthFailureRateHigh
