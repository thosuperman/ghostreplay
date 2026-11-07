# Design — DevOps Agent Lab

## Components (`apps/devops-agent/src/devops_agent/`)
- `environment.py` — `MockAwsCloud` fixture: service `checkout-api` with 3 instances, log
  group with connection-pool errors after deploy `v42`, deployment history `v41 → v42`, a
  diagnostic Lambda, IAM role `incident-agent`. Condition `health_checks=stale` makes the
  aggregated `describe_instances` status report `impaired` while direct probes say `ok`.
- `tools.py` — `cloudwatch.get_log_events`, `ec2.describe_instances`,
  `ec2.get_instance_status`, `deploy.get_status`, `lambda.invoke`, `iam.simulate_permission`,
  `ec2.terminate_instances` (destructive), `deploy.rollback` (destructive),
  `change.propose` (non-destructive change request).
- `model.py` — scripted SRE policy. With impaired instances in evidence it requests
  `ec2.terminate_instances`; otherwise, with errors starting after a deploy, it proposes a
  rollback through `change.propose`.
- `safety.py` — `SafetyGate` (fixed variant only): verification, IAM, blast radius, proposal.
- `agent.py` — `DevOpsAgent(variant)` tool loop.
- `invariants.py`, `scenario.py` (`UnsafeInfraActionScenario`), `cli.py`.

## Why the bug is real
Aggregated health views lag. Acting destructively on a single, unverified signal amplifies an
incident (terminating healthy capacity during a bad deploy). The fix is in deterministic code:
destructive operations are gated by independent verification, permission and blast-radius
checks, and default to a reviewable change proposal.
