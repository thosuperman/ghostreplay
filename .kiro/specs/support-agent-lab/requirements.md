# Requirements — Support Agent Lab (Duplicate Refund)

## Introduction
A customer-support agent looks up an order, checks refund eligibility, issues a refund through
a simulated payment API and replies to the customer. The payment gateway can time out *after*
committing a refund. A naive retry produces a second refund. The app must be built only on
`ghostreplay` and run independently (`uv run support-agent-lab serve`, port 8101).

## Requirement 1 — Workflow
1.1 The agent SHALL perform: order lookup → eligibility check → refund → customer reply.
1.2 All data SHALL come from a simulated orders database and a simulated payment API.
1.3 The decision maker SHALL be a scripted model shared by both variants and labelled scripted.

## Requirement 2 — Vulnerable variant
2.1 WHEN `payments.create_refund` times out THEN the vulnerable harness SHALL retry the identical
    request without an idempotency key (the bug under study).
2.2 WHEN the gateway committed the first attempt THEN the simulated ledger SHALL contain two
    refunds for the same payment.

## Requirement 3 — Fixed variant
3.1 The fixed harness SHALL send an intent-scoped idempotency key
    (`refund:<ticket>:<payment>:<amount>`) with every attempt.
3.2 WHEN a refund attempt times out THEN the fixed harness SHALL reconcile by listing refunds
    for the payment before retrying, and SHALL reuse the same key on retry.
3.3 The simulated payment API SHALL honour idempotency keys (same key → original refund).

## Requirement 4 — Invariants
4.1 `refund.no_duplicate` — at most one refund per payment in the final ledger.
4.2 `refund.within_order_total` — refunded total ≤ order total.
4.3 `refund.retries_are_idempotent` — repeated refund calls for one payment carry one key.
4.4 `reply.matches_ledger` — the customer reply states the amount actually refunded.
4.5 `errors.surfaced` — unrecovered tool errors are reflected in the final status.

## Requirement 5 — Conditions and fault presets
5.1 Condition `payment_gateway`: `healthy` | `timeout_after_commit` (incident).
5.2 Presets: refund timeout after commit (headline), timeout before commit, gateway 429,
    missing order total, stale eligibility.

## Acceptance criteria
- Incident recording with the vulnerable variant FAILS `refund.no_duplicate`.
- Offline replay of the incident reproduces it with zero diff entries.
- Counterfactual `timeout_after_commit` on a healthy recording: vulnerable FAIL, fixed PASS.
- Generated regression case for the fixed variant passes under pytest.
