# Runbook: TLS certificate expiring or expired

Use this when a TLS certificate is close to expiry or has expired: public edge certificates in ACM,
internal mTLS certificates issued by cert-manager, or a client certificate used to call a partner.

## Symptoms
- Alert from the certificate monitor: days to expiry below 14 (warning) or 3 (critical).
- After expiry: browsers show `NET::ERR_CERT_DATE_INVALID`; clients log
  `x509: certificate has expired or is not yet valid` or `PKIX path validation failed`.
- Sudden 100% failure on one hostname or one service-to-service path, with no deploy.
- cert-manager `Certificate` resource shows `Ready=False` with a renewal error.

## Impact
- Expired public certificate: the site is unreachable for most users. SEV1.
- Expired internal mTLS: one internal path breaks fully (for example checkout to payments).
- Before expiry there is no impact; this is the cheapest time to fix it.

## Diagnosis steps
All steps are read-only.
1. Check the served certificate: `openssl s_client -connect <host>:443 -servername <host> </dev/null | openssl x509 -noout -dates -issuer -subject`
2. ACM: `aws acm describe-certificate --certificate-arn <arn>` and check `NotAfter`, `RenewalSummary`
   and whether DNS validation records still exist (missing CNAME blocks auto-renewal).
3. cert-manager: `kubectl get certificate -A` and `kubectl describe certificate <name> -n <ns>`;
   check the `CertificateRequest` and the Issuer status (ACME challenge failures, rate limits).
4. Check if the renewed certificate exists but was not picked up: services that load certificates
   only at startup need a restart.

## Mitigation
- ACM with missing validation record: restore the CNAME; renewal completes within hours.
- cert-manager: fix the Issuer (credentials, DNS solver permissions) and trigger renewal.
- If the new certificate exists but the app has the old one cached, do a rolling restart.
- Emergency for public endpoint: import a manually issued certificate into ACM and attach to the
  load balancer (needs approval from Security).

## Rollback
- If a manually imported certificate was attached, switch back to the ACM-managed one after renewal
  and delete the manual one.

## Escalation
- Platform team for cert-manager and ingress.
- Security team for any manual certificate issuance.
- Partner contact if a partner's certificate expired.

## Related alerts
- TLSCertExpiringSoon
- TLSCertExpired
- CertManagerCertificateNotReady
