# Implementation plan — DevOps Agent Lab

> Tasks marked `[x]` predate this spec; open `[ ]` tasks are carried out in Kiro (prompts:
> `docs/kiro-demo-prompts.md`).

- [x] 1. Package `devops-agent-lab` on the uv workspace, depending only on `ghostreplay`
  - Entry points: script `devops-agent-lab`, `ghostreplay.scenarios` → `unsafe-infra-action`,
    `ghostreplay.labs` → `devops`
  - _Requirements: 1.2_

- [x] 2. `MockAwsCloud` fixture with the `health_checks` condition
  - Tests: `test_no_real_aws_access_possible`
  - _Requirements: 1.2, 5.1_

- [x] 3. Tools (read-only, destructive, proposal) with Pydantic argument models
  - Tests: `test_offline_tool_registry_refuses_destructive_handlers`
  - _Requirements: 1.1, 1.2_

- [x] 4. Scripted SRE model `sre-sim-1`
  - Tests: `test_healthy_run_proposes_rollback_for_both_variants`, `test_missing_evidence_leads_to_escalation`
  - _Requirements: 1.3, 1.4, 6.1_

- [x] 5. Agent harness and `SafetyGate` for the fixed variant
  - Tests: `test_incident_terminates_healthy_fleet`, `test_fixed_agent_blocks_action_under_incident_conditions`, `test_safety_gate_blocks_fleet_wide_termination_under_stale_health`
  - _Requirements: 2.1, 2.2, 3.1, 3.2, 3.3_

- [x] 6. Invariants: verification, capacity, approval, errors surfaced
  - Tests: `test_counterfactual_misleading_health`, `test_one_stale_instance_still_flagged_even_with_capacity_left`, `test_permission_denied_is_reported_not_hidden`
  - _Requirements: 4.1–4.4, 6.2, 6.3_

- [x] 7. Scenario, five presets, CLI (`serve`, `run`, `demo`, `export-cases`)
  - Tests: `test_demo_story`
  - _Requirements: 5.1, 5.2_

- [x] 8. Offline replay of the incident is identical and never touches the cloud
  - Tests: `test_incident_replay_is_identical_and_offline`, `test_destructive_action_replays_without_touching_the_cloud`
  - _Requirements: 6.4_

- [x] 9. Committed regression cases (`tests/regression/unsafe-infra-action-incorrect-output-{vulnerable,fixed}.case.json` + generated test modules)
  - _Requirements: 6.2_

- [x] 10. Invariant `infra.approval_chain_valid`
  - 10.1 Write failing tests first in `apps/devops-agent/tests/test_unsafe_infra_action.py`:
    `test_self_approved_change_violates_approval_chain`,
    `test_human_approved_change_satisfies_approval_chain`,
    `test_proposal_without_evidence_violates_approval_chain`
  - 10.2 Implement the invariant in `invariants.py` and add it to `all_invariants()`
  - 10.3 Confirm every existing test and committed case keeps its outcome
  - Verify: `uv run pytest apps/devops-agent/tests -q -x && uv run ghostreplay test tests/regression`
  - _Requirements: 7.1–7.5_

- [x] 11. `probe-timeout` preset and honest recovery in the SafetyGate
  - 11.1 Write `test_probe_timeout_blocks_and_is_reported_as_recovered` (fails today on
    `errors.surfaced` for the fixed variant)
  - 11.2 Add the preset to `UnsafeInfraActionScenario.fault_presets()`
  - 11.3 Log `recovered` with `recovers: <probe event id>` in `SafetyGate.review` when a probe
    fails and the action is blocked
  - Verify: `uv run pytest apps/devops-agent/tests -q -x && uv run devops-agent-lab --db /tmp/gr demo`
  - _Requirements: 8.1, 8.2, 8.3_
