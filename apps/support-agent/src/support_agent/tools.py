"""Tools exposed to the support agent.

Reads are SQL queries against the run's SQLite database; refunds are real HTTP requests to the
local refund service (see ``environment.py``). ``build_tools(None)`` returns the same tool
specifications without a world, for strict offline replay where no handler may run.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from ghostreplay import HttpError
from ghostreplay.mocking import ToolRegistry, ToolSpec

from .environment import CLIENT_TIMEOUT_MS, SupportWorld


class LookupOrder(BaseModel):
    order_id: str = Field(pattern=r"^ORD-\d{3,8}$")


class CheckEligibility(BaseModel):
    order_id: str = Field(pattern=r"^ORD-\d{3,8}$")
    sku: str


class CreateRefund(BaseModel):
    payment_id: str
    amount_cents: int = Field(gt=0, le=1_000_000)
    reason: str
    sku: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=200)


class ListRefunds(BaseModel):
    payment_id: str


class SendReply(BaseModel):
    customer_id: str
    ticket_id: str
    message: str = Field(max_length=4000)


def build_tools(world: SupportWorld | None) -> ToolRegistry:
    reg = ToolRegistry()

    def timed(fn):  # record real wall-clock latency of real I/O as the event's duration
        def run(*a, **k):
            t0 = time.perf_counter()
            try:
                return fn(*a, **k)
            finally:
                if world is not None:
                    world.clock.advance(round((time.perf_counter() - t0) * 1000, 1))

        return run

    def w() -> SupportWorld:
        if world is None:  # pragma: no cover - offline registries never call handlers
            raise RuntimeError("no world: this registry is for offline replay only")
        return world

    def lookup_order(order_id: str) -> dict[str, Any]:
        order = w().order(order_id)
        if order is None:
            raise HttpError(f"orders-db: order {order_id} not found", data={"status": 404})
        return {**order, "customer": w().customer(order["customer_id"])}

    def create_refund(
        payment_id: str,
        amount_cents: int,
        reason: str,
        sku: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "payment_id": payment_id,
            "amount_cents": amount_cents,
            "reason": reason,
            "sku": sku,
        }
        return w().post_refund(body, idempotency_key)

    def list_refunds(payment_id: str) -> dict[str, Any]:
        return w().get_refunds(payment_id)

    def send_reply(customer_id: str, ticket_id: str, message: str) -> dict[str, Any]:
        return w().queue_reply(customer_id, ticket_id, message)

    def ledger_for(args: dict[str, Any]) -> dict[str, Any]:
        return w().ledger(args.get("payment_id"))

    reg.register(
        ToolSpec(
            "orders.lookup_order",
            timed(lookup_order),
            "Fetch an order and its customer.",
            "database",
            args_model=LookupOrder,
        )
    )
    reg.register(
        ToolSpec(
            "refunds.check_eligibility",
            timed(lambda order_id, sku: w().eligibility(order_id, sku)),
            "Apply the refund policy to one order line.",
            "agent",
            args_model=CheckEligibility,
        )
    )
    reg.register(
        ToolSpec(
            "payments.create_refund",
            timed(create_refund),
            "Issue a refund through the payment gateway (moves money).",
            "http",
            destructive=True,
            args_model=CreateRefund,
            timeout_ms=CLIENT_TIMEOUT_MS,
            observe=ledger_for,
        )
    )
    reg.register(
        ToolSpec(
            "payments.list_refunds",
            timed(list_refunds),
            "List refunds already issued for a payment.",
            "http",
            args_model=ListRefunds,
        )
    )
    reg.register(
        ToolSpec(
            "crm.send_reply",
            timed(send_reply),
            "Send the reply to the customer.",
            "agent",
            args_model=SendReply,
        )
    )
    return reg
