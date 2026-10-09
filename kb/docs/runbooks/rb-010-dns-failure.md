# Runbook: DNS resolution failures (CoreDNS / Route 53)

Use this when services cannot resolve hostnames: internal service names inside the cluster
(CoreDNS) or external names such as RDS endpoints and third-party APIs.

## Symptoms
- Errors like `getaddrinfo ENOTFOUND`, `no such host`, `Temporary failure in name resolution`,
  `UnknownHostException`.
- Failures are intermittent and spread across many services at once, not one.
- CoreDNS metrics: `coredns_dns_responses_total{rcode="SERVFAIL"}` rising, request latency high,
  CoreDNS pods CPU-throttled or restarting.
- Lookups take seconds; outbound calls time out before connecting.

## Impact
- Wide blast radius: any service that resolves names per request is affected.
- Often looks like a dependency outage. Check DNS before blaming the dependency.
- SEV1 if checkout or payments cannot resolve their dependencies.

## Diagnosis steps
All steps are read-only.
1. From a debug pod, test resolution and timing:
   `kubectl run dnscheck --rm -it --image=busybox:1.36 --restart=Never -- nslookup orders-db.internal`
   (creates a temporary pod; allowed for diagnosis).
2. Check CoreDNS health: `kubectl get pods -n kube-system -l k8s-app=kube-dns` and their logs for
   `i/o timeout` to upstream resolvers.
3. Check CoreDNS saturation: CPU throttling, QPS per pod. High `ndots:5` settings multiply queries
   (each external name tried with every search domain first).
4. Check node conntrack table usage: UDP DNS packets dropped when `nf_conntrack` is full.
5. Check Route 53 Resolver and VPC DNS limits (1024 packets per second per ENI) for bursts.
6. Check recent changes: CoreDNS ConfigMap edits, new stub domains, Route 53 private zone changes.

## Mitigation
- Scale CoreDNS replicas up, or enable NodeLocal DNSCache if available.
- Revert a recent CoreDNS ConfigMap change.
- For heavy external lookups, set `ndots: 2` on the affected workload or use fully qualified names
  with a trailing dot.

## Rollback
- Revert CoreDNS replica count after the incident only if load is back to normal.
- Revert ConfigMap or Route 53 record changes made during the incident if they were temporary.

## Escalation
- Platform team (owns CoreDNS and VPC DNS).
- AWS support if Route 53 or VPC resolver is degraded (check the AWS Health Dashboard).

## Related alerts
- CoreDNSErrorsHigh
- CoreDNSLatencyHigh
- NodeConntrackTableFull
