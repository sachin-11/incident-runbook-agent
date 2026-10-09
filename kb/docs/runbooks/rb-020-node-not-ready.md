# Runbook: Kubernetes node NotReady

Use this when one or more worker nodes go `NotReady`. Pods on those nodes stop receiving traffic
and are rescheduled after the eviction timeout (5 minutes by default).

## Symptoms
- `kubectl get nodes` shows `NotReady` for one or more nodes.
- Pods on the node show `Unknown` or `Terminating` status for a long time.
- Events: `NodeNotReady`, `Kubelet stopped posting node status`.
- Often all NotReady nodes share one AZ or one node group/AMI version.

## Impact
- Reduced capacity until pods reschedule. If many nodes fail together, pods stay Pending.
- StatefulSets with volumes on that node wait for volume detach (several minutes).
- SEV2 if more than 20% of nodes are NotReady.

## Diagnosis steps
All steps are read-only.
1. `kubectl describe node <node>` and read Conditions (`MemoryPressure`, `DiskPressure`,
   `PIDPressure`, `NetworkUnavailable`) and recent events.
2. Check the EC2 instance: status checks (`aws ec2 describe-instance-status --instance-ids <id>`),
   scheduled events, Spot interruption notices.
3. Check whether the nodes share a recent AMI or launch template change.
4. Check the AWS Health Dashboard for EC2 or EBS issues in that AZ.
5. Check kubelet and container runtime logs through SSM if the instance is reachable.

## Mitigation
- Cordon and drain affected nodes so workloads move (drain needs approval).
- If an AZ is impaired, scale node groups in the healthy AZs.
- If a new AMI is the cause, roll the launch template back.

## Rollback
- Revert the launch template / AMI version and replace nodes created from the bad version.

## Escalation
- Platform team on-call.
- AWS support if instance status checks fail or Health Dashboard shows an AZ issue.

## Related alerts
- KubeNodeNotReady
- EC2InstanceStatusCheckFailed
- KubePodsPendingInsufficientCPU
