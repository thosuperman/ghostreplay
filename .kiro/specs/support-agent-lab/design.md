# Design — Support Agent Lab

Written after the implementation; it records the decisions in the current code and the design
of the planned tasks.

## Components (`apps/support-agent/src/support_agent/`)

| File | Responsibility |
|---|---|
| `environment.py` | `SupportWorld`: `MockDatabase` (orders `ORD-1042` with two lines, customers), `payments-gateway` `MockHttpService` with `POST /v1/refunds` (Idempotency-Key aware, 409 on key reuse with other params, refundable-amount check) and `GET /v1/refunds?payment_id=`; `eligibility()` policy (30-day window, already-refunded check); `snapshot()` for final state. The incident condition adds a `ChaosRule("POST", "/v1/refunds", "commit_then_timeout", latency_ms=10_000)`. |
| `tools.py` | `orders.lookup_order` (database), `refunds.check_eligibility`, `payments.create_refund` (http, destructive, `timeout_ms=10_000`, observes the ledger), `payments.list_refunds`, `crm.send_reply`; Pydantic argument models. |
| `model.py` | `support-sim-1` scripted policy: reads tool results from the conversation and picks the next call or the final reply; escalates on missing/invalid eligibility data. |
| `agent.py` | `SupportAgent(variant)`: shared loop; `_refund_naive` (vulnerable) vs `_refund_idempotent` (fixed). |
| `invariants.py` | five invariants (`refund.*`, `reply.matches_ledger`, `errors.surfaced`). |
| `scenario.py` | `DuplicateRefundScenario` (condition, variants, six presets, explanations). |
| `cli.py` | `build_lab(store)` (also the `ghostreplay.labs` entry point `support`) and `main`. |

## Decisions and rationale

### D1 — The bug lives in the harness, not the model
Both variants share `support-sim-1`. *Rationale:* the lesson is that ambiguous failures must be
handled by deterministic code; a fix that depends on the model "being smarter" would not be
provable by a regression test.

### D2 — Intent-scoped idempotency key
`refund:<ticket>:<payment>:<amount>` instead of a random UUID. *Rationale:* a random key per
attempt is no key at all; a key per process dies with the process. Deriving it from the
business intent means every retry — even after a restart — maps to the same gateway record.

### D3 — Reconcile before retry
After a timeout the fixed harness lists refunds and returns the committed one if its key is
present (logging `recovered` with `recovers: <event id>`, which also satisfies
`errors.surfaced`). The key alone would already make the retry safe; reconciliation avoids
an unnecessary second POST and makes the recovery visible in the trace.

### D4 — A gateway that behaves like a real one
Idempotency, 409 on key misuse and the refundable-amount check are implemented in the
simulation. *Rationale:* the fix is only meaningful if the simulated server enforces the same
contract real payment APIs do; `test_retry_with_same_idempotency_key_returns_the_original_refund`
and siblings pin that contract down.

### D5 — State-based invariants for money
`refund.no_duplicate`, `within_order_total` and `reply.matches_ledger` read the final ledger,
not the trace, so they cannot be fooled by how the agent narrates its actions; offline they are
`inconclusive`, which is why the headline counterfactual runs in branch mode.

## Planned design — Requirement 7 (`refund.within_line_total`)
- Invariant reads order lines from `final_state["orders"]` (already part of
  `SupportWorld.snapshot()`), maps each refund's `payment_id` to its order and compares the
  refunded total per SKU with `price_cents * qty`. No snapshot change is needed.
- Preset `eligibility-inflated-amount` in `fault_presets()`.
- Fixed harness: before `create_refund`, compare `amount_cents` with the line total from the
  `orders.lookup_order` result in the conversation (or call it again) and return a structured
  error `amount_exceeds_line_total` so the model escalates. Vulnerable stays unchanged — it is
  the detector's target.
- Rationale: `within_order_total` protects the merchant's captured total, not the per-item
  intent; the inflated-eligibility fault shows the gap (verified: both variants currently refund
  $288.00 with all five invariants passing).

## Planned design — Requirement 8 (partial-refund variant)
- New `Condition("damage", "Damage type", ("broken", "cosmetic"), "broken", "broken", ...)`.
- `SupportWorld(clock, payment_gateway=..., damage=...)`; `eligibility()` halves the refundable
  amount for `cosmetic` and sets `reason: "partial_cosmetic"`.
- The scripted policy already refunds `refundable_amount_cents`; the reply already quotes the
  refunded amount, so no model change is expected.
- Risk: adding a condition changes `resolve_conditions()` output for new recordings (the
  deterministic seed includes conditions). Committed cases embed their reference and keep their
  own conditions; verify with `uv run ghostreplay test tests/regression`.

## Test coverage map (`apps/support-agent/tests/test_duplicate_refund.py`)

| Requirement | Tests |
|---|---|
| 1.1–1.3, 6.5 | `test_healthy_run_passes_for_both_variants`, `test_counterfactual_fails_vulnerable_and_passes_fixed`, `test_demo_story` |
| 1.4 | `test_other_presets_are_handled_safely_by_fixed_agent` (parametrized over presets) |
| 2.1 | `test_retry_without_idempotency_key_creates_a_duplicate_refund`, `test_retry_with_same_idempotency_key_returns_the_original_refund`, `test_reusing_idempotency_key_with_different_amount_is_rejected` |
| 2.2 | `test_gateway_never_refunds_more_than_was_captured` |
| 2.3 | `test_timeout_after_commit_really_commits_before_the_client_times_out` |
| 3.1–3.2, 6.3 | `test_incident_reproduces_duplicate_refund`, `test_timeout_before_commit_hides_the_bug`, `test_cli_run_exit_codes` |
| 4.1–4.3 | `test_fixed_agent_survives_incident_conditions`, `test_counterfactual_fails_vulnerable_and_passes_fixed` |
| 5.x | asserted across the tests above (`statuses(ex)[...]`) |
| 6.4 | `test_incident_replays_offline_identically`, `test_replaying_the_duplicate_refund_never_touches_the_gateway`, `test_strict_counterfactual_does_not_invent_continuation` |
| regression | `tests/regression/test_duplicate_refund_timeout_after_commit_vulnerable.py`, `tests/regression/test_duplicate_refund_timeout_after_commit_fixed.py` |

## Verification

```bash
uv run pytest apps/support-agent/tests -q
uv run pytest tests/regression -q -k duplicate_refund
uv run support-agent-lab --db /tmp/gr-support demo          # exit 0, "Demo check passed"
uv run support-agent-lab --db /tmp/gr-support run --incident  # exit 1: vulnerable fails
uv run support-agent-lab --db /tmp/gr-support run --incident --variant fixed  # exit 0
```
