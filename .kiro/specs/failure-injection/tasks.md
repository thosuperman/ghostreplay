# Implementation plan — Failure injection and regression proof

> **Provenance.** Tasks marked `[x]` were implemented before this repository was opened in
> Kiro; this spec was written afterwards to document them, and each one was checked against
> the current code and tests. Unchecked `[ ]` tasks are real, not-yet-done improvements
> intended to be executed in Kiro (prompts: `docs/kiro-demo-prompts.md`).

- [x] 1. Fault catalog (13 kinds) with strategies and `requires_branch`
  - `mutation/catalog.py`; served at `GET /api/faults`
  - Tests: `test_catalog_covers_required_faults`, `test_unknown_fault_kind_rejected`
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Fault targeting and application
  - `FaultPlan.match` (kind, name, occurrence, `where`); `apply_fault` for `error`,
    `transform` (JSON paths with `*`), `execute_then_error`, `delay`; `AppliedFault` keeps the
    original response/error; `substituted` replay verdict
  - Tests: `test_occurrence_targets_only_that_call`, `test_transform_faults`, `test_error_and_delay_faults`
  - _Requirements: 2.1–2.5_

- [x] 3. Counterfactual modes
  - `Lab.counterfactual(mode="auto"|"replay"|"branch")`; offline refusal of `requires_branch`
    faults; strict replay stops at divergence with an explanatory note; branch re-executes and
    verifies against the recording
  - Tests: `test_offline_counterfactual_stops_instead_of_inventing_a_continuation`, `test_same_fault_in_branch_mode_executes_continuation`, `test_branch_without_faults_stays_on_track_and_verifies_tools`, `test_requires_branch_faults_are_rejected_offline`, `test_branch_fault_reproduces_double_withdrawal_and_fix_prevents_it`, `test_mutation_that_invalidates_the_recorded_path_stops_offline_replay`, `test_same_mutation_in_branch_mode_runs_the_new_path_and_labels_it`
  - _Requirements: 3.1–3.5_

- [x] 4. Invariant framework
  - `Invariant`, `Check`, `TraceView`; `requires_state` → `inconclusive` offline;
    `errors_surfaced`, `max_successful_calls`
  - Tests: `test_offline_counterfactual_stops_instead_of_inventing_a_continuation` (inconclusive), app invariant tests
  - _Requirements: 4.1–4.3_

- [x] 5. Regression cases, runner, generation and reports
  - `RegressionCase` (data only, embedded reference), `case_from_execution`, `run_case`
    (in-memory lab, registry resolution), `write_case`, `pytest_source`, JSON + JUnit XML,
    `ghostreplay test` exit status; committed cases in `tests/regression/`
  - Tests: `test_case_generation_runs_and_reports`, `test_malformed_case_file_is_rejected`, `test_http_api_end_to_end`, the four generated modules in `tests/regression/`
  - _Requirements: 5.1–5.6_

- [x] 6. Self-checking guided demo
  - `prepare_demo` (six steps), `DemoStep.expected` / `as_expected`, `DemoStory.ok`; CLI
    `demo` prints the failing step and exits 1
  - Tests: `test_demo_story` (framework and both apps), `test_demo_story_reports_whether_every_step_met_expectations`; CI demo steps
  - _Requirements: 6.1–6.3_

- [x] 7. Lab CLI `run` and `export-cases`
  - Tests: `test_cli_run_exit_codes`; CI "Freshly generated regression cases" step
  - _Requirements: 7.1, 7.2_

- [ ] 8. Add the `reordered_response` fault kind
  - 8.1 Catalog entry in `mutation/catalog.py` (strategy `transform`, `requires_branch=False`,
    params `path`, `rotate`)
  - 8.2 Behaviour in `mutation/faults.py::_transform` (reverse by default, rotate when
    `rotate` is given; note when the path is missing or not a list)
  - 8.3 Tests in `packages/ghostreplay/tests/test_mutation.py`: reversal, rotation, missing
    path; add `reordered_response` to `test_catalog_covers_required_faults`; assert
    `GET /api/faults` lists it (`TestClient(create_app(lab))`)
  - 8.4 Dashboard: `DEFAULT_PARAMS.reordered_response = {}` in
    `apps/dashboard/src/views/FailureLab.tsx`; typecheck passes
  - 8.5 Docs: add the row to the catalog table in `docs/architecture.md`; update the
    "13 kinds" count in `README.md`
  - Verify: `uv run pytest packages/ghostreplay/tests -q -x` and
    `corepack pnpm --dir apps/dashboard typecheck`
  - _Requirements: 8.1, 8.2, 8.3, 1.3_

- [ ] 9. Add the `clock_skew` fault kind for nondeterminism
  - 9.1 Extend `FaultTarget.kind` with `"nondeterminism"` in `models/faults.py`; mirror in
    `apps/dashboard/src/api/types.ts` (schema-sync hook)
  - 9.2 Catalog entry + `_transform` branch shifting the ISO timestamp by `skew_ms`
  - 9.3 Test with the toy-bank scenario: skewing `clock.now` is applied, recorded as
    `injected`, and an offline counterfactual still matches the remaining recording
  - 9.4 Failure Lab lists `nondeterminism` events as targets when `clock_skew` is selected
  - Verify: `uv run pytest packages/ghostreplay/tests -q -x` and
    `corepack pnpm --dir apps/dashboard typecheck`
  - _Requirements: 9.1, 9.2, 9.3_

- [ ] 10. `export-cases --preset` and a pytest for the demo exit status
  - 10.1 `server/cli.py`: `--preset` option for `export-cases`; unknown id → message + exit 2
  - 10.2 Tests in `apps/support-agent/tests/test_duplicate_refund.py` and
    `apps/devops-agent/tests/test_unsafe_infra_action.py`: `main(["--db", tmp, "demo"]) == 0`;
    `export-cases --preset gateway-rate-limited` (support) writes two cases that pass
    `ghostreplay test`
  - Verify: `uv run pytest apps -q -x` and
    `uv run support-agent-lab --db /tmp/gr export-cases --preset gateway-rate-limited --out /tmp/gr-cases && uv run ghostreplay test /tmp/gr-cases`
  - _Requirements: 6.3, 10.1, 10.2_
