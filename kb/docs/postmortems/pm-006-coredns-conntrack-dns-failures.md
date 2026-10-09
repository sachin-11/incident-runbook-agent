# Postmortem: Intermittent DNS failures from conntrack exhaustion (2026-08-30)

## Summary
During a flash sale, request volume tripled. Each external call did up to 5 DNS lookups because of
`ndots:5`. UDP DNS traffic filled the nodes' `nf_conntrack` tables, packets were dropped, and many
services logged `Temporary failure in name resolution` for 31 minutes.

## Symptoms
- Intermittent `UnknownHostException` / `getaddrinfo EAI_AGAIN` across checkout, payments and
  search at the same time.
- CoreDNS SERVFAIL and latency up; kernel log `nf_conntrack: table full, dropping packet`.
- Outbound calls timed out before connecting.

## Impact
- Elevated error rates across tier-1 services; checkout error rate peaked at 12%. SEV1.

## Timeline
- 20:00 flash sale starts, traffic 3x.
- 20:06 CoreDNSErrorsHigh and multiple service error alerts.
- 20:15 first suspicion of payment provider outage (wrong lead, provider healthy).
- 20:24 conntrack drops found in node logs.
- 20:30 CoreDNS scaled 2 -> 6; NodeLocal DNSCache enabled on one node group.
- 20:37 errors back to baseline.

## Root cause
DNS-heavy clients (`ndots:5`, no caching) plus small conntrack limits on the node AMI.

## Diagnosis steps
- `nslookup` timing from a debug pod; CoreDNS metrics; kernel logs via SSM.

## Mitigation
- Scaled CoreDNS and enabled NodeLocal DNSCache.

## Rollback
- None; changes kept.

## Escalation
- Platform on-call, incident commander.

## Action items
- Roll out NodeLocal DNSCache to all node groups.
- Set `ndots:2` in base pod templates.
- Alert on conntrack usage above 80%.

## Related alerts
- CoreDNSErrorsHigh
- NodeConntrackTableFull
- CoreDNSLatencyHigh
