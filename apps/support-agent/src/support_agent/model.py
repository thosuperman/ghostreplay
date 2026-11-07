"""Scripted support model.

A deterministic policy that stands in for an LLM so the demo runs offline and for free. It
reads the conversation — including structured tool results — and decides the next tool call
or the final reply. It is labelled 'scripted' in every execution; it is not a live model.
"""

from __future__ import annotations

import re
from typing import Any

from ghostreplay.mocking import Message, ModelRequest, ModelResponse, ScriptedModel, ToolCallRequest

MODEL_NAME = "support-sim-1"

SYSTEM_PROMPT = (
    "You are a customer-support agent for an electronics store. Look up the order, check the "
    "refund policy for the item the customer mentions, issue a refund only if eligible, and "
    "reply to the customer with exactly what was done."
)

_ITEM_HINTS = {"earbud": "AUR-EB-01", "lamp": "LUM-DL-02"}


def _last_tool(messages: list[Message], name: str) -> Any:
    for m in reversed(messages):
        if m.role == "tool" and m.name == name:
            return m.data
    return None


def _call(i: int, name: str, **arguments: Any) -> ModelResponse:
    return ModelResponse(
        tool_calls=[ToolCallRequest(id=f"call_{i}", name=name, arguments=arguments)],
        stop_reason="tool_use",
    )


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def support_policy(req: ModelRequest) -> ModelResponse:
    user = next(m.content for m in req.messages if m.role == "user")
    step = sum(1 for m in req.messages if m.role == "tool") + 1
    order = _last_tool(req.messages, "orders.lookup_order")
    elig = _last_tool(req.messages, "refunds.check_eligibility")
    refund = _last_tool(req.messages, "payments.create_refund")

    if order is None:
        match = re.search(r"ORD-\d+", user)
        if not match:
            return ModelResponse(
                content="Could you share your order number (ORD-…)? I can then help."
            )
        return _call(step, "orders.lookup_order", order_id=match.group(0))

    if isinstance(order, dict) and "error" in order:
        return ModelResponse(
            content="I'm sorry — I couldn't open your order just now. I've escalated your request "
            "to a specialist who will follow up within one business day."
        )

    if elig is None:
        sku = next((s for hint, s in _ITEM_HINTS.items() if hint in user.lower()), None)
        if sku is None:
            return ModelResponse(content="Which item from your order would you like refunded?")
        return _call(step, "refunds.check_eligibility", order_id=order["order_id"], sku=sku)

    if "error" in elig:
        return ModelResponse(
            content="I couldn't verify the refund policy for your item, so I've escalated your "
            "request to a specialist instead of guessing."
        )
    if not elig.get("eligible"):
        return ModelResponse(
            content=f"I'm sorry, this item isn't eligible for a refund ({elig.get('reason')})."
        )
    amount = elig.get("refundable_amount_cents")
    if not isinstance(amount, int) or amount <= 0:
        return ModelResponse(
            content="I couldn't determine the refundable amount for your item, so I've escalated "
            "your request rather than refund an unverified amount."
        )

    if refund is None:
        return _call(
            step,
            "payments.create_refund",
            payment_id=elig["payment_id"],
            amount_cents=amount,
            reason="damaged_on_arrival",
            sku=elig["sku"],
        )

    if isinstance(refund, dict) and "error" not in refund:
        item = next((i["name"] for i in order["items"] if i["sku"] == elig["sku"]), "item")
        return ModelResponse(
            content=f"Hi {order['customer']['name'].split()[0]}, I'm sorry your {item} arrived "
            f"damaged. I've refunded {_money(refund['amount_cents'])} to your original payment "
            f"method (refund {refund['id']}). It should appear within 5–10 business days."
        )
    return ModelResponse(
        content="The payment system didn't confirm your refund, so I've escalated to our billing "
        "team to make sure it's handled exactly once."
    )


def build_model() -> ScriptedModel:
    return ScriptedModel(MODEL_NAME, support_policy)
