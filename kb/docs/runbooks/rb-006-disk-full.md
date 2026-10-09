# Runbook: Disk full (node ephemeral storage or database volume)

Use this when a filesystem fills up: Kubernetes node root disk, a pod's ephemeral storage, or the
RDS storage volume. Writes start failing once free space reaches zero.

## Symptoms
- `No space left on device` (ENOSPC) in application or database logs.
- Node condition `DiskPressure=True`; kubelet evicts pods with
  `The node was low on resource: ephemeral-storage`.
- RDS `FreeStorageSpace` dropping fast; Postgres logs `could not extend file`.
- Log shipping stops because the agent cannot write its buffer.

## Impact
- On nodes: pods get evicted and rescheduled; image pulls fail on that node.
- On the database: all writes fail; this is SEV1 for orders-db.
- Logs may be lost for the period the disk was full.

## Diagnosis steps
All steps are read-only.
1. Nodes: `kubectl describe node <node>` and look at `Conditions` and `Allocated resources`.
2. Find the pods using the most ephemeral storage:
   `kubectl get pods -A -o wide --field-selector spec.nodeName=<node>`, then check each pod's
   `ephemeral-storage` usage in the metrics dashboard.
3. Typical culprits: verbose debug logging written to the container filesystem, core dumps,
   temp files from report generation, unrotated log files, container image layers on a small root
   volume.
4. RDS: check `FreeStorageSpace` trend, table and index bloat, `pg_wal` growth caused by an
   inactive replication slot (`SELECT slot_name, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) FROM pg_replication_slots;`).
5. Check whether storage autoscaling is enabled on the RDS instance and its maximum.

## Mitigation
- Node: cordon the node so no new pods land there, then let evictions or a drain move workloads
  (drain is a write action and needs approval).
- Pod: lower log level back to INFO; set an `ephemeral-storage` limit so one pod cannot fill a node.
- RDS: increase allocated storage (online, needs approval); drop an inactive replication slot
  only with DBA approval because it breaks that replica's stream.

## Rollback
- Uncordon the node after cleanup.
- Revert any debug logging flag that caused the growth.
- Storage increases on RDS cannot be reverted; note it in the incident record.

## Escalation
- Platform team for node disk.
- DBA on-call for RDS storage; SEV1 if orders-db free storage is under 5%.

## Related alerts
- NodeDiskPressure
- DiskUsageCritical
- RDSFreeStorageSpaceLow
