"""Tools exposed to the support agent (all backed by the simulated world)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

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


def build_tools(world: SupportWorld) -> ToolRegistry:
    reg = ToolRegistry()

    def lookup_order(order_id: str) -> dict[str, Any]:
        order = world.db.get("orders", order_id)
        customer = world.db.get("customers", order["customer_id"])
        return {
            **order,
            "customer": {"customer_id": customer["customer_id"], "name": customer["name"]},
        }

    def create_refund(
        payment_id: str,
        amount_cents: int,
        reason: str,
        sku: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        return world.gateway.request(
            "POST",
            "/v1/refunds",
            json={
                "payment_id": payment_id,
                "amount_cents": amount_cents,
                "reason": reason,
                "sku": sku,
            },
            headers=headers,
        )

    def list_refunds(payment_id: str) -> dict[str, Any]:
        return world.gateway.request("GET", "/v1/refunds", params={"payment_id": payment_id})

    def send_reply(customer_id: str, ticket_id: str, message: str) -> dict[str, Any]:
        world.clock.advance(35)
        msg = {
            "id": f"msg_{len(world.outbox) + 1:03d}",
            "customer_id": customer_id,
            "ticket_id": ticket_id,
            "message": message,
            "channel": "email (simulated)",
        }
        world.outbox.append(msg)
        return {"queued": True, "message_id": msg["id"]}

    def ledger_for(args: dict[str, Any]) -> dict[str, Any]:
        pid = args.get("payment_id")
        refunds = [r for r in world.refunds if r["payment_id"] == pid]
        return {
            "payment_id": pid,
            "refund_count": len(refunds),
            "refunded_cents": sum(r["amount_cents"] for r in refunds),
            "refund_ids": [r["id"] for r in refunds],
        }

    reg.register(
        ToolSpec(
            "orders.lookup_order",
            lookup_order,
            "Fetch an order and its customer.",
            "database",
            args_model=LookupOrder,
        )
    )
    reg.register(
        ToolSpec(
            "refunds.check_eligibility",
            lambda order_id, sku: world.eligibility(order_id, sku),
            "Apply the refund policy to one order line.",
            "agent",
            args_model=CheckEligibility,
        )
    )
    reg.register(
        ToolSpec(
            "payments.create_refund",
            create_refund,
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
            list_refunds,
            "List refunds already issued for a payment.",
            "http",
            args_model=ListRefunds,
        )
    )
    reg.register(
        ToolSpec(
            "crm.send_reply",
            send_reply,
            "Send the reply to the customer.",
            "agent",
            args_model=SendReply,
        )
    )
    return reg
