# Kiro prompts for the open spec tasks

Ready-to-paste prompts for Kiro chat. Each one leads to a real code change plus tests and
closes one open (`[ ]`) task in `.kiro/specs/`. Start the task from its `tasks.md` in Kiro, then
paste the prompt so the agent has the acceptance criteria and verification commands together.
See `docs/kiro-workflow.md` for how to capture evidence.

Every prompt assumes the steering files are loaded. Add `#competition` when you want the scope
and honesty rules in context.

---

## 1. New fault kind: `reordered_response`

**Closes:** `failure-injection` task 8 (and the `reordered_response` half of `dashboard` task 16)

```text
Implement the `reordered_response` fault kind described in .kiro/specs/failure-injection
(requirement 8, task 8).

Goal: a replay-safe transform fault that reverses (default) or rotates (`rotate: int`) the list
at `path` in a tool response (default: the first list found).

Files to touch:
- packages/ghostreplay/src/ghostreplay/mutation/catalog.py  (new FaultKind entry: strategy
  "transform", requires_branch=False, params path + rotate)
- packages/ghostreplay/src/ghostreplay/mutation/faults.py   (_transform branch; reuse
  _first_list_path; return a note when the path is missing or not a list)
- packages/ghostreplay/tests/test_mutation.py               (tests below)
- apps/dashboard/src/views/FailureLab.tsx                   (DEFAULT_PARAMS entry)
- docs/architecture.md and README.md                        (catalog table, "13 kinds" count)

Acceptance criteria:
- WHEN applied with no params to a response containing one list THE list is reversed and the
  original response is kept on AppliedFault.original_response (test apply_fault directly, as
  test_transform_faults does).
- WHEN rotate=1 THE list is rotated left by one.
- WHEN path does not exist THE response is unchanged and the applied fault description says so.
- GET /api/faults lists reordered_response (test with TestClient(create_app(lab))).
- test_catalog_covers_required_faults includes the new kind.
- An offline counterfactual (mode="replay") accepts the fault (requires_branch is False).

Write the tests first and show them failing, then implement.

Verify:
  uv run pytest packages/ghostreplay/tests -q -x
  corepack pnpm --dir apps/dashboard typecheck
  uv run ruff check . && uv run ruff format --check .
Then tick task 8 in .kiro/specs/failure-injection/tasks.md.
```

## 2. Better divergence detection

### 2a. Name the exact field in `result_mismatch`

**Closes:** `replay-engine` task 11

```text
Implement .kiro/specs/replay-engine task 11 (requirements 3.6, 10.1, 10.2).

Goal: when a branch run's re-executed tool returns a different result than the recording,
the `result_mismatch` divergence message names the first differing response/error path(s),
the same way Session._check already does for changed inputs.

Files to touch:
- packages/ghostreplay/src/ghostreplay/replay/session.py   (Session._verify message)
- packages/ghostreplay/tests/test_edge_cases.py            (new test)

Acceptance criteria:
- New test test_branch_reports_the_first_differing_result_field: record a toy-bank run, edit one
  recorded tool_call response in the stored execution (e.g. a balance value), save it under a new
  id, run lab.counterfactual(new_id, [], mode="branch"), and assert
  divergence.type == "result_mismatch" and the edited path appears in divergence.message.
- Existing tests keep passing; no change to the Divergence schema.

Show the new test failing before the change.

Verify:
  uv run pytest packages/ghostreplay/tests -q -x
  uv run ruff check . && uv run ruff format --check .
```

### 2b. Recompute and verify match keys on load

**Closes:** `replay-engine` task 12

```text
Implement .kiro/specs/replay-engine task 12 (requirements 4.3, 9.1–9.3), following the
"Planned design — Requirement 9" section of .kiro/specs/replay-engine/design.md.

Files to touch:
- packages/ghostreplay/src/ghostreplay/replay/verify.py  (new: recompute_match_keys)
- packages/ghostreplay/src/ghostreplay/storage/files.py  (import_execution(..., strict=False))
- packages/ghostreplay/src/ghostreplay/cli.py            (`ghostreplay verify <files...>`)
- packages/ghostreplay/tests/test_edge_cases.py          (tests)

Acceptance criteria:
- An untouched exported trace verifies clean (CLI exit 0).
- Editing a recorded request without updating match_key is reported with its seq, kind and name;
  strict import raises TraceFormatError; CLI exits 1.
- Tools that declare match_fields are hashed over that subset only.
- A document with a duplicate event_id (but increasing seq) is rejected — add a dedicated test.

Verify:
  uv run pytest packages/ghostreplay/tests -q -x
  uv run ruff check . && uv run ruff format --check .
Manual check: export a recording with ghostreplay.storage.export_execution (as the tests do)
and run `uv run ghostreplay verify <file>.trace.json`.
```

## 3. New safety invariants (failing first, then passing)

### 3a. Support: refunds bounded by the order line

**Closes:** `support-agent-lab` task 10

```text
Implement .kiro/specs/support-agent-lab task 10 (requirement 7).

Context: injecting incorrect_output on refunds.check_eligibility with
set={"refundable_amount_cents": 28800} makes BOTH variants refund $288.00 for the $129.00
earbuds, and all five current invariants pass. That is the gap.

Files to touch:
- apps/support-agent/src/support_agent/invariants.py  (refund.within_line_total, critical,
  requires_state; order lines are in final_state["orders"])
- apps/support-agent/src/support_agent/scenario.py    (preset eligibility-inflated-amount)
- apps/support-agent/src/support_agent/agent.py       (fixed harness refuses an amount above the
  order line and returns a structured error so the model escalates; vulnerable unchanged)
- apps/support-agent/tests/test_duplicate_refund.py   (tests)

Acceptance criteria:
- First add test_inflated_eligibility_is_caught_and_fixed_agent_escalates and run it to show it
  fails.
- Vulnerable + preset: refund.within_line_total == "failed" with the refund event as evidence.
- Fixed + preset: no refund in the ledger, output.status == "escalated", every invariant passes.
- Healthy runs, the incident tests and the committed regression cases keep their outcomes.

Verify:
  uv run pytest apps/support-agent/tests -q -x
  uv run pytest tests/regression -q
  uv run support-agent-lab --db /tmp/gr demo
```

### 3b. DevOps: approval-chain invariant

**Closes:** `devops-agent-lab` task 10

```text
Implement .kiro/specs/devops-agent-lab task 10 (requirement 7): invariant
infra.approval_chain_valid in apps/devops-agent/src/devops_agent/invariants.py.

Rules: an approved change must have approved_by set, different from requested_by and from the
agent role "incident-agent"; an executed destructive call that references change_id must match
that change's action; every successful change.propose must carry non-empty evidence.

Write these tests first in apps/devops-agent/tests/test_unsafe_infra_action.py and show them
failing: test_self_approved_change_violates_approval_chain,
test_human_approved_change_satisfies_approval_chain,
test_proposal_without_evidence_violates_approval_chain. Build the inputs from a real healthy
recording (lab.record) and edit final_state / events on a copy; evaluate with the invariant's
evaluate(execution).

Acceptance criteria: the three tests pass; all existing devops tests and committed regression
cases keep their outcomes; the invariant appears in GET /lab/devops/api/scenarios.

Verify:
  uv run pytest apps/devops-agent/tests -q -x
  uv run ghostreplay test tests/regression
```

### 3c. DevOps: probe timeouts inside the SafetyGate

**Closes:** `devops-agent-lab` task 11

```text
Implement .kiro/specs/devops-agent-lab task 11 (requirement 8).

Context: with the misleading-health fault plus tool_timeout on every ec2.get_instance_status
call, the fixed agent correctly blocks the termination but reports success with unrecovered
probe errors, so errors.surfaced FAILS.

Files to touch: apps/devops-agent/src/devops_agent/scenario.py (preset probe-timeout),
apps/devops-agent/src/devops_agent/safety.py (log "recovered" with recovers=<probe event id>
when a probe fails and the action is blocked), apps/devops-agent/tests/test_unsafe_infra_action.py.

Acceptance criteria:
- test_probe_timeout_blocks_and_is_reported_as_recovered fails before the change and passes
  after: fixed variant executes no destructive call, records the blocked_destructive_action
  guard, files no termination proposal, and every invariant passes; vulnerable variant still
  fails infra.capacity_preserved.
- Do not weaken errors.surfaced itself.

Verify:
  uv run pytest apps/devops-agent/tests -q -x
  uv run devops-agent-lab --db /tmp/gr demo
```

## 4. Dashboard: execution inspector

**Closes:** `dashboard` task 14 (task 15 has a smaller variant below)

```text
Implement .kiro/specs/dashboard task 14 (requirement 8).

Goal: in the execution Inspector (apps/dashboard/src/components/execution.tsx), for model_call
events show response.usage (token or character counts) and response.served_by when present, and
add a "Copy as JSON" button for the selected event.

Constraints: TypeScript strict, no `any` (narrow from Json/unknown); reuse Badge/Stat/Button from
components/ui.tsx; copy pattern as in views/Regression.tsx; accessible button name
"Copy as JSON".

Tests: extend apps/dashboard/e2e/flows.spec.ts — record a run, open it, click the first model
call in the timeline, assert the usage block and the "Copy as JSON" button are visible.

Verify:
  corepack pnpm --dir apps/dashboard typecheck
  corepack pnpm --dir apps/dashboard e2e
```

Smaller variant (dashboard task 15):

```text
Implement .kiro/specs/dashboard task 15: in views/Explorer.tsx show a `live` or `scripted` badge
per execution from ExecutionSummary.model_provider, and extend the explorer e2e test to assert
`scripted` on a freshly recorded run. Verify with typecheck and `corepack pnpm --dir
apps/dashboard e2e`.
```

## 5. Generate and execute a regression test

**Closes:** `failure-injection` task 10

```text
Implement .kiro/specs/failure-injection task 10 (requirements 6.3, 10.1, 10.2).

Files to touch:
- packages/ghostreplay/src/ghostreplay/server/cli.py (export-cases --preset <id>; unknown id →
  list known presets, exit 2)
- apps/support-agent/tests/test_duplicate_refund.py and
  apps/devops-agent/tests/test_unsafe_infra_action.py (tests)

Acceptance criteria:
- main(["--db", tmp, "demo"]) returns 0 for both labs (new tests).
- `support-agent-lab export-cases --preset gateway-rate-limited --out <tmp>` writes a vulnerable
  case (expect FAIL) and a fixed case (expect PASS); `ghostreplay test <tmp>` reports 2/2 cases
  matched expectations; the generated pytest modules pass.
- An unknown preset exits 2 without writing files.

Then generate and run the regression cases end to end:
  uv run support-agent-lab --db /tmp/gr-x export-cases --preset gateway-rate-limited --out /tmp/gr-cases
  uv run ghostreplay test /tmp/gr-cases --junit /tmp/gr-cases/junit.xml --json /tmp/gr-cases/report.json
  uv run pytest /tmp/gr-cases -q
  uv run pytest apps -q -x
Do not commit the /tmp cases; only commit regenerated tests/regression files if the task
deliberately changes them.
```

## 6. Remaining open tasks (short prompts)

- **`failure-injection` task 9 — `clock_skew`:** "Implement task 9 of
  .kiro/specs/failure-injection: allow FaultTarget.kind 'nondeterminism', add a replay-safe
  clock_skew transform (skew_ms), test it with the toy-bank scenario, let the schema-sync hook
  update apps/dashboard/src/api/types.ts, and list nondeterminism events as Failure Lab targets
  for this kind. Verify with `uv run pytest packages/ghostreplay/tests -q -x` and the dashboard
  typecheck."
- **`support-agent-lab` task 11 — partial refund:** "Implement task 11 of
  .kiro/specs/support-agent-lab: add the `damage` condition (broken | cosmetic, 50 % refund for
  cosmetic) and test_partial_refund_timeout_after_commit (vulnerable FAILS refund.no_duplicate,
  fixed PASSES, reply states $64.50). Verify with `uv run pytest apps/support-agent/tests -q -x`,
  `uv run ghostreplay test tests/regression` and `uv run support-agent-lab --db /tmp/gr demo`."
