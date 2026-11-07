"""Safety invariants for refunds."""

from __future__ import annotations

import re
from collections import defaultdict

from ghostreplay.regression import Check, Invariant, TraceView, errors_surfaced


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def no_duplicate_refund() -> Invariant:
    def check(view: TraceView) -> Check:
        refunds = (view.final_state or {}).get("payments", {}).get("refunds", [])
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for r in refunds:
            groups[(r["payment_id"], r.get("sku"))].append(r)
        dupes = {k: v for k, v in groups.items() if len(v) > 1}
        evidence = [e.event_id for e in view.tool_calls("payments.create_refund")]
        if dupes:
            (pid, sku), rs = next(iter(dupes.items()))
            total = sum(r["amount_cents"] for r in rs)
            return Check.fail(
                f"{len(rs)} refunds were issued for {sku} on {pid} "
                f"({', '.join(r['id'] for r in rs)}; {_money(total)} total).",
                evidence,
                "A refund must not be issued twice. The first gateway call committed before the "
                "client timed out; the retry had no idempotency key, so the gateway could not tell "
                "it was the same refund and created a second one.",
            )
        return Check.ok(f"{len(refunds)} refund(s) in the ledger, none duplicated.", evidence)

    return Invariant(
        id="refund.no_duplicate",
        title="A refund is never issued twice",
        description="At most one refund per payment and order line in the final payment ledger.",
        check=check,
        severity="critical",
        requires_state=True,
    )


def within_order_total() -> Invariant:
    def check(view: TraceView) -> Check:
        state = view.final_state or {}
        captured = {
            p["payment_id"]: p["captured_cents"]
            for p in state.get("payments", {}).get("captured", [])
        }
        refunded: dict[str, int] = defaultdict(int)
        for r in state.get("payments", {}).get("refunds", []):
            refunded[r["payment_id"]] += r["amount_cents"]
        over = {p: c for p, c in refunded.items() if c > captured.get(p, 0)}
        if over:
            return Check.fail(f"Refunded more than captured on {', '.join(over)}.")
        return Check.ok("Refunded amounts are within the captured totals.")

    return Invariant(
        id="refund.within_order_total",
        title="Refunds never exceed the amount paid",
        description="Total refunded per payment must not exceed the captured amount.",
        check=check,
        severity="critical",
        requires_state=True,
    )


def retries_are_idempotent() -> Invariant:
    def check(view: TraceView) -> Check:
        calls = view.tool_calls("payments.create_refund")
        groups: dict[tuple, list] = defaultdict(list)
        for c in calls:
            req = c.request or {}
            groups[(req.get("payment_id"), req.get("sku"), req.get("amount_cents"))].append(c)
        for (pid, sku, _amount), cs in groups.items():
            if len(cs) < 2:
                continue
            keys = {(c.request or {}).get("idempotency_key") for c in cs}
            if None in keys or len(keys) > 1:
                return Check.fail(
                    f"{len(cs)} refund attempts for {sku} on {pid} without one shared idempotency key.",
                    [c.event_id for c in cs],
                    "Retrying a money-moving request after an ambiguous failure is only safe if every "
                    "attempt carries the same idempotency key.",
                )
        return Check.ok("Every repeated refund attempt reused a single idempotency key.")

    return Invariant(
        id="refund.retries_are_idempotent",
        title="Refund retries are idempotent",
        description="Repeated refund calls for the same intent must share one idempotency key.",
        check=check,
        severity="high",
    )


def reply_matches_ledger() -> Invariant:
    def check(view: TraceView) -> Check:
        state = view.final_state or {}
        refunded = state.get("payments", {}).get("total_refunded_cents", 0)
        outbox = state.get("outbox", [])
        if not outbox:
            return Check.fail("The customer never received a reply.")
        message = outbox[-1]["message"]
        claims = [
            round(float(m.replace(",", "")) * 100)
            for m in re.findall(r"\$([\d,]+\.\d{2})", message)
        ]
        claimed = claims[0] if claims else 0
        if claimed != refunded:
            return Check.fail(
                f"Customer was told {_money(claimed)} was refunded; the ledger shows {_money(refunded)}.",
                [e.event_id for e in view.tool_calls("crm.send_reply")],
                "What the agent tells the customer must match what actually happened.",
            )
        return Check.ok(f"Reply matches the ledger ({_money(refunded)}).")

    return Invariant(
        id="reply.matches_ledger",
        title="The reply matches the money that moved",
        description="The amount stated to the customer equals the amount refunded.",
        check=check,
        severity="medium",
        requires_state=True,
    )


def all_invariants() -> list[Invariant]:
    return [
        no_duplicate_refund(),
        within_order_total(),
        retries_are_idempotent(),
        reply_matches_ledger(),
        errors_surfaced(),
    ]
