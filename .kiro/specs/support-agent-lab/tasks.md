# Implementation plan — Support Agent Lab

> **Provenance.** Tasks marked `[x]` were implemented before this repository was opened in
> Kiro; this spec was written afterwards to document them, and each one was checked against
> the current code and tests. Unchecked `[ ]` tasks are real, not-yet-done improvements
> intended to be executed in Kiro (prompts: `docs/kiro-demo-prompts.md`).

- [x] 1. Package `support-agent-lab` on the uv workspace, depending only on `ghostreplay`
  - Entry points: script `support-agent-lab`, `ghostreplay.scenarios` → `duplicate-refund`,
    `ghostreplay.labs` → `support`
  - _Requirements: 1.2_

- [x] 2. Simulated world and payment gateway contract
  - Orders DB, Idempotency-Key semantics (replay / 409), refundable-amount check,
    `timeout_after_commit` chaos rule, ledger snapshot
  - Tests: `test_retry_without_idempotency_key_creates_a_duplicate_refund`, `test_retry_with_same_idempotency_key_returns_the_original_refund`, `test_reusing_idempotency_key_with_different_amount_is_rejected`, `test_gateway_never_refunds_more_than_was_captured`, `test_timeout_after_commit_really_commits_before_the_client_times_out`
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 3. Tools with Pydantic argument models and ledger observation
  - _Requirements: 1.1, 1.2_

- [x] 4. Scripted model `support-sim-1` (labelled scripted, escalates on unverified data)
  - Tests: `test_other_presets_are_handled_safely_by_fixed_agent`
  - _Requirements: 1.3, 1.4_

- [x] 5. Agent harness: vulnerable retry and fixed idempotent refund with reconciliation
  - Tests: `test_incident_reproduces_duplicate_refund`, `test_fixed_agent_survives_incident_conditions`, `test_timeout_before_commit_hides_the_bug`
  - _Requirements: 3.1, 3.2, 4.1, 4.2, 4.3_

- [x] 6. Invariants: `refund.no_duplicate`, `refund.within_order_total`,
  `refund.retries_are_idempotent`, `reply.matches_ledger`, `errors.surfaced`
  - _Requirements: 5.1–5.5_

- [x] 7. Scenario, six fault presets, CLI (`serve`, `run`, `demo`, `export-cases`)
  - Tests: `test_counterfactual_fails_vulnerable_and_passes_fixed`, `test_strict_counterfactual_does_not_invent_continuation`, `test_demo_story`, `test_cli_run_exit_codes`
  - _Requirements: 6.1, 6.2, 6.5_

- [x] 8. Offline replay of the incident is identical and never touches the gateway
  - Tests: `test_incident_replays_offline_identically`, `test_replaying_the_duplicate_refund_never_touches_the_gateway`
  - _Requirements: 6.4_

- [x] 9. Committed regression cases (`tests/regression/duplicate-refund-timeout-after-commit-{vulnerable,fixed}.case.json` + generated test modules)
  - _Requirements: 6.5_

- [ ] 10. Invariant `refund.within_line_total` + preset `eligibility-inflated-amount`
  - 10.1 Write the failing test first in `apps/support-agent/tests/test_duplicate_refund.py`:
    `test_inflated_eligibility_is_caught_and_fixed_agent_escalates` (vulnerable FAILS
    `refund.within_line_total`; fixed refunds nothing and escalates; all fixed invariants pass)
  - 10.2 Add the invariant to `invariants.py` and `all_invariants()` (order lines are already
    in the final-state snapshot under `orders`)
  - 10.3 Add the preset to `DuplicateRefundScenario.fault_presets()`
  - 10.4 Fixed harness: refuse an amount above the order line before calling
    `payments.create_refund`
  - 10.5 Re-run committed cases (`uv run ghostreplay test tests/regression`) — the new invariant
    must not change their expected outcomes
  - Verify: `uv run pytest apps/support-agent/tests -q -x && uv run pytest tests/regression -q`
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 11. Partial-refund variant (`damage=cosmetic`)
  - 11.1 Add the `damage` condition and the 50 % eligibility rule
  - 11.2 Test `test_partial_refund_timeout_after_commit` : under `damage=cosmetic` the headline
    preset makes the vulnerable variant FAIL `refund.no_duplicate` (two $64.50 refunds) and the
    fixed variant PASS, with the reply stating $64.50
  - 11.3 Confirm `uv run support-agent-lab demo` still exits 0 and committed cases still pass
  - Verify: `uv run pytest apps/support-agent/tests -q -x && uv run ghostreplay test tests/regression`
  - _Requirements: 8.1, 8.2, 8.3, 8.4_
