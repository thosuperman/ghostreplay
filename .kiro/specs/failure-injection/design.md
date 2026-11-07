# Design — Failure injection and regression proof

Written after the implementation; it records the decisions in the current code and the design
of the planned tasks.

## Components

| Concern | Module | Key types / functions |
|---|---|---|
| Catalog | `mutation/catalog.py` | `FaultKind(id, title, description, strategy, requires_branch, params)`, `CATALOG`, `get_kind` |
| Matching and application | `mutation/faults.py` | `FaultPlan.match`, `apply_fault` → `FaultOutcome`, `_make_error`, `_transform`, `expand_paths` (`*` wildcard) |
| Fault data | `models/faults.py`, `models/events.py` | `FaultSpec`, `FaultTarget`, `FaultPreset`, `AppliedFault` |
| Counterfactual orchestration | `lab/lab.py` | `Lab.counterfactual(mode=auto|replay|branch)`, `Lab._execute` |
| Invariants | `regression/invariants.py` | `Invariant`, `Check.ok/fail/unknown`, `TraceView`, `errors_surfaced`, `max_successful_calls` |
| Cases | `regression/cases.py`, `regression/runner.py`, `regression/generate.py` | `RegressionCase`, `RegressionReport.explain`, `load_case`, `run_case`, `write_case`, `pytest_source`, `reports_to_json`, `reports_to_junit` |
| Demo story | `lab/lab.py` | `Lab.prepare_demo`, `DemoStep.expected/as_expected`, `DemoStory.ok` |
| CLIs | `server/cli.py`, `cli.py` | `lab_main` (`run`, `demo`, `export-cases`, `serve`), `ghostreplay test` |

## Decisions and rationale

### D1 — Strategies, not ad-hoc fault code
Four strategies cover every kind: `error` (synthetic error, nothing executes), `transform`
(edit the baseline response by JSON path), `execute_then_error` (really execute, then report a
failure), `delay` (execute after added latency; past the tool timeout the agent sees a
timeout). *Rationale:* new kinds are a catalog entry plus a small branch, and the dashboard can
render any kind from `/api/faults` without knowing it in advance.

### D2 — `requires_branch` is a hard gate
Faults whose meaning depends on a real side effect (`timeout_after_commit`, `partial_success`,
`delayed_operation`) are rejected in offline modes (`Session.__init__`, `apply_fault`).
*Rationale:* faking "the refund committed" offline would be a fabricated outcome — exactly what
the product promises never to do.

### D3 — Offline counterfactuals stop at divergence
After a fault changes behaviour, the recording no longer describes what the agent will do.
Strict mode records the divergence and stops; notes tell the user to use branch mode.
*Rationale:* the alternative (guessing the continuation) produces convincing but invented
traces.

### D4 — Branch mode is real execution, verified while on-track
Branch rebuilds the scenario's simulated world, re-executes tools and compares each result to
the recording until the first divergence. Model calls and nondeterminism come from the
recording while on-track, so the run is the same run up to the fault. After divergence the
scenario's model adapter runs for real and events are labelled `simulated`.

### D5 — Invariants judge outcomes, inconclusive is a first-class answer
Invariants read a `TraceView` (events + final state + output). State-dependent invariants are
`inconclusive` when no state exists. Regression reports never count inconclusive as passed.

### D6 — Cases are data with an embedded reference
A case embeds the reference execution and names the scenario by id; the generated pytest module
is a fixed 15-line template that loads the JSON. *Rationale:* reviewable diffs, no executable
content in data files, and cases replay identically on CI without a database.

### D7 — The demo checks itself
`DemoStep.expected` encodes what the story needs (incident FAIL, replay PASS, counterfactual
FAIL, fix PASS, proof PASS). `DemoStory.ok` drives both the dashboard warning and the CLI exit
status, so CI fails if a change silently breaks the narrative.

## Planned design — `reordered_response` (Requirement 8)
- Catalog entry: strategy `transform`, `requires_branch=False`, params
  `{"path": "list path (default: first list found)", "rotate": "rotate by N instead of reversing"}`.
- `_transform`: reuse `_first_list_path`; `items[::-1]` or `items[n:] + items[:n]`; return
  `(data, note)` with a note when the path is missing or not a list.
- Dashboard: add `reordered_response: {}` to `DEFAULT_PARAMS` in
  `apps/dashboard/src/views/FailureLab.tsx`; the kind list itself comes from `/api/faults`.
- Rationale: order-dependent agents (e.g. "terminate the first impaired instance") are a real
  failure class not covered by `duplicate_response`.

## Planned design — `clock_skew` (Requirement 9)
- `FaultTarget.kind: Literal["tool_call", "model_call", "nondeterminism"]` (schema change →
  schema-sync hook → `types.ts` update).
- Catalog: strategy `transform`, `requires_branch=False`, params `{"skew_ms": "milliseconds to
  add (negative = past)"}`; `_transform` parses the ISO string with `datetime.fromisoformat`.
- Failure Lab target list must include `nondeterminism` events when this kind is selected.
- Rationale: expiry, refund-window and "freshness" checks depend on time; skew is a realistic
  failure that today cannot be injected.

## Planned design — `export-cases --preset` (Requirement 10)
- `lab_main`: `e.add_argument("--preset")`; resolve with `scenario.preset(id)`; on `ValueError`
  print the known preset ids and return 2.
- Test both labs' `main(["--db", tmp, "demo"]) == 0` and an unknown preset returning 2.

## Test coverage map

| Requirement | Tests (file :: function) |
|---|---|
| 1.1–1.2, 1.4 | `packages/ghostreplay/tests/test_mutation.py` :: `test_catalog_covers_required_faults`, `test_unknown_fault_kind_rejected` |
| 1.3 | no direct test of `GET /api/faults` yet (the dashboard Failure Lab consumes it) — added by task 8 |
| 2.1 | `test_mutation.py` :: `test_occurrence_targets_only_that_call` |
| 2.2–2.4 | `test_mutation.py` :: `test_transform_faults`, `test_error_and_delay_faults`, `test_branch_fault_reproduces_double_withdrawal_and_fix_prevents_it`; `apps/support-agent/tests/test_duplicate_refund.py` :: `test_timeout_after_commit_really_commits_before_the_client_times_out` |
| 3.1–3.2 | `test_mutation.py` :: `test_offline_counterfactual_stops_instead_of_inventing_a_continuation`, `test_requires_branch_faults_are_rejected_offline`; `test_edge_cases.py` :: `test_mutation_that_invalidates_the_recorded_path_stops_offline_replay`; `test_duplicate_refund.py` :: `test_strict_counterfactual_does_not_invent_continuation` |
| 3.3–3.4 | `test_mutation.py` :: `test_same_fault_in_branch_mode_executes_continuation`, `test_branch_without_faults_stays_on_track_and_verifies_tools`; `test_edge_cases.py` :: `test_same_mutation_in_branch_mode_runs_the_new_path_and_labels_it` |
| 4.1–4.3 | `test_mutation.py` :: `test_offline_counterfactual_stops_instead_of_inventing_a_continuation` (asserts `inconclusive`); `test_duplicate_refund.py` :: `test_strict_counterfactual_does_not_invent_continuation`, `test_other_presets_are_handled_safely_by_fixed_agent` (`errors.surfaced`); `test_unsafe_infra_action.py` :: `test_permission_denied_is_reported_not_hidden`; `max_successful_calls` has no dedicated test yet |
| 5.1–5.6 | `test_diff_regression_server.py` :: `test_case_generation_runs_and_reports`, `test_http_api_end_to_end`; `test_edge_cases.py` :: `test_malformed_case_file_is_rejected`; committed cases `tests/regression/test_duplicate_refund_timeout_after_commit_{vulnerable,fixed}.py`, `tests/regression/test_unsafe_infra_action_incorrect_output_{vulnerable,fixed}.py` |
| 6.1–6.2 | `test_diff_regression_server.py` :: `test_demo_story`; `test_edge_cases.py` :: `test_demo_story_reports_whether_every_step_met_expectations`; app `test_demo_story` tests |
| 6.3 | CI steps "Demo — Duplicate Refund" / "Demo — Unsafe Infrastructure Action" (no pytest yet — task 10) |
| 7.1 | `apps/support-agent/tests/test_duplicate_refund.py` :: `test_cli_run_exit_codes` |
| 7.2 | CI step "Freshly generated regression cases" |

## Verification

```bash
uv run pytest packages/ghostreplay/tests/test_mutation.py packages/ghostreplay/tests/test_edge_cases.py -q
uv run pytest tests/regression -q
uv run ghostreplay test tests/regression --junit reports/junit.xml --json reports/report.json
uv run support-agent-lab --db /tmp/gr-demo demo && uv run devops-agent-lab --db /tmp/gr-demo demo
uv run support-agent-lab --db /tmp/gr-export export-cases --out /tmp/gr-cases \
  && uv run ghostreplay test /tmp/gr-cases && uv run pytest /tmp/gr-cases -q
```
