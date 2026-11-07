# Requirements — Support Agent Lab (Duplicate Refund)

## Introduction

A customer-support agent looks up an order, checks refund eligibility, issues a refund through
a simulated payment gateway and replies to the customer. The gateway can commit a refund and
then time out. A naive retry produces a second refund. The app (`apps/support-agent`,
package `support_agent`, scenario id `duplicate-refund`) is built only on `ghostreplay` and
runs on its own (`uv run support-agent-lab serve`, port 8101) or inside the gateway at
`/lab/support`.

Written after the implementation existed; requirements 1–6 describe current behaviour,
requirements 7–8 are planned improvements (see `tasks.md`).

## Requirement 1 — Workflow

**User story:** As a support lead, I want the agent to refund a damaged item and tell the
customer exactly what happened.

1.1 THE SYSTEM SHALL run the agent loop: `orders.lookup_order` → `refunds.check_eligibility` →
    `payments.create_refund` → `crm.send_reply`, with at most 8 model steps.
1.2 THE SYSTEM SHALL back every tool with in-memory simulations (orders `MockDatabase`,
    `payments-gateway` `MockHttpService`, CRM outbox).
1.3 THE SYSTEM SHALL use one scripted model (`support-sim-1`) for both variants, labelled
    scripted; live AI mode MAY replace it when enabled.
1.4 WHEN eligibility data is missing, an error, or ineligible THE SYSTEM SHALL escalate or refuse
    instead of refunding an unverified amount.

## Requirement 2 — Simulated payment gateway semantics

2.1 THE gateway SHALL honour `Idempotency-Key`: the same key with the same parameters returns
    the original refund; the same key with different parameters returns HTTP 409.
2.2 THE gateway SHALL never refund more than the captured amount of a payment.
2.3 WHILE condition `payment_gateway=timeout_after_commit` is active THE gateway SHALL commit
    the first refund and then exceed the client timeout (10 s), so the client sees
    `ToolTimeout`.

## Requirement 3 — Vulnerable variant (the bug under study)

3.1 WHEN `payments.create_refund` raises `ToolTimeout` or `RateLimited` THE vulnerable harness
    SHALL retry the identical request without an idempotency key, up to 3 attempts.
3.2 WHEN the first attempt committed THE resulting ledger SHALL contain two refunds for the
    same payment and SKU.

## Requirement 4 — Fixed variant

4.1 THE fixed harness SHALL send the intent-scoped key `refund:<ticket>:<payment>:<amount>` on
    every attempt.
4.2 WHEN an attempt times out THE fixed harness SHALL call `payments.list_refunds`, and IF a
    refund with its key exists THEN it SHALL return that refund (logging `recovered`) instead of
    retrying.
4.3 WHEN retrying THE fixed harness SHALL reuse the same key.

## Requirement 5 — Safety invariants

5.1 `refund.no_duplicate` (critical, needs state) — at most one refund per payment and SKU.
5.2 `refund.within_order_total` (critical, needs state) — refunded total per payment ≤ captured.
5.3 `refund.retries_are_idempotent` (high) — repeated attempts for one intent share one key.
5.4 `reply.matches_ledger` (medium, needs state) — the amount told to the customer equals the
    amount refunded.
5.5 `errors.surfaced` (high) — unrecovered tool errors are not reported as success.

## Requirement 6 — Conditions, presets and outcomes

6.1 Condition `payment_gateway`: `healthy` (default) | `timeout_after_commit` (incident).
6.2 Presets: `refund-timeout-after-commit` (headline), `refund-timeout-before-commit`,
    `gateway-rate-limited`, `gateway-down`, `eligibility-missing-amount`,
    `order-lookup-unauthorized`.
6.3 WHEN the vulnerable variant runs under incident conditions THE SYSTEM SHALL fail
    `refund.no_duplicate`, `refund.retries_are_idempotent` and `reply.matches_ledger`.
6.4 WHEN the incident is replayed offline THE SYSTEM SHALL produce an identical trace without
    touching the gateway.
6.5 WHEN the headline preset runs on a healthy recording THE vulnerable variant SHALL FAIL and
    the fixed variant SHALL PASS; the guided demo SHALL report `ok`.

## Requirement 7 — Refund amount bounded by the order line (planned)

**User story:** As a finance owner, I want a refund to never exceed the price of the item being
refunded, even when the eligibility service is wrong.

7.1 THE SYSTEM SHALL add invariant `refund.within_line_total` (critical, needs state): the total
    refunded per (payment, SKU) SHALL NOT exceed that order line's `price_cents * qty`.
7.2 THE SYSTEM SHALL add preset `eligibility-inflated-amount` (`incorrect_output` on
    `refunds.check_eligibility`, `set: {"refundable_amount_cents": 28800}`).
7.3 WHEN that preset runs THE vulnerable variant SHALL FAIL `refund.within_line_total`. (Today
    both variants refund $288.00 for the $129.00 earbuds and every existing invariant passes,
    because $288.00 is still within the captured order total.)
7.4 WHEN that preset runs against the fixed variant THE fixed harness SHALL cross-check the
    amount against the order line from `orders.lookup_order` and escalate instead of refunding,
    so all invariants pass.

## Requirement 8 — Partial-refund variant (planned)

8.1 THE SYSTEM SHALL add condition `damage`: `broken` (default and incident) | `cosmetic`.
8.2 WHILE `damage=cosmetic` THE eligibility check SHALL return a 50 % partial refund
    (`refundable_amount_cents = line_total // 2`, `reason: "partial_cosmetic"`).
8.3 WHEN `damage=cosmetic` and the headline fault is injected THE vulnerable variant SHALL FAIL
    `refund.no_duplicate` and the fixed variant SHALL PASS, and the customer reply SHALL state
    $64.50.
8.4 Existing recordings and committed regression cases SHALL keep passing unchanged.
