"""Simulated world for the support agent: an orders database and a payment gateway.

Everything is in memory. The payment gateway behaves like a real one in the ways that
matter here: it enforces the refundable amount, honours ``Idempotency-Key`` headers (same key
returns the original refund; same key with different parameters is a 409), and can suffer an
ambiguous failure where the refund commits but the client never receives the response.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from ghostreplay.core.clock import Clock
from ghostreplay.mocking import ChaosRule, HttpRequest, HttpResponse, MockDatabase, MockHttpService

ORDERS = [
    {
        "order_id": "ORD-1042",
        "customer_id": "CUS-0077",
        "status": "delivered",
        "placed_at": "2026-10-20T14:03:00+00:00",
        "delivered_at": "2026-10-24T10:12:00+00:00",
        "currency": "USD",
        "payment_id": "pay_3KQ81",
        "items": [
            {"sku": "AUR-EB-01", "name": "Aurora wireless earbuds", "qty": 1, "price_cents": 12900},
            {"sku": "LUM-DL-02", "name": "Lumen desk lamp", "qty": 1, "price_cents": 15900},
        ],
        "total_cents": 28800,
    }
]
CUSTOMERS = [
    {
        "customer_id": "CUS-0077",
        "name": "Maya Chen",
        "email": "maya.chen@example.com",
        "tier": "plus",
    }
]
PAYMENTS = [
    {
        "payment_id": "pay_3KQ81",
        "order_id": "ORD-1042",
        "captured_cents": 28800,
        "currency": "USD",
        "status": "captured",
    }
]

REFUND_WINDOW_DAYS = 30
CLIENT_TIMEOUT_MS = 10_000


class SupportWorld:
    def __init__(self, clock: Clock, *, payment_gateway: str = "healthy") -> None:
        self.clock = clock
        self.db = MockDatabase(clock)
        self.db.create_table("orders", ORDERS, pk="order_id")
        self.db.create_table("customers", CUSTOMERS, pk="customer_id")
        self.payments_table = {p["payment_id"]: copy.deepcopy(p) for p in PAYMENTS}
        self.refunds: list[dict[str, Any]] = []
        self.idempotency: dict[str, dict[str, Any]] = {}
        self.outbox: list[dict[str, Any]] = []
        self.gateway = MockHttpService("payments-gateway", clock, base_latency_ms=180)
        self._routes()
        if payment_gateway == "timeout_after_commit":
            # Incident condition: the gateway commits the first refund, then hangs past the
            # client's timeout, so the client never learns that it succeeded.
            self.gateway.chaos.append(
                ChaosRule(
                    "POST", "/v1/refunds", "commit_then_timeout", latency_ms=CLIENT_TIMEOUT_MS
                )
            )

    # -- payment gateway --------------------------------------------------------------------
    def _routes(self) -> None:
        gw = self.gateway

        @gw.route("POST", "/v1/refunds")
        def create_refund(req: HttpRequest) -> HttpResponse:
            body = req.json or {}
            key = req.header("Idempotency-Key")
            params = {k: body.get(k) for k in ("payment_id", "amount_cents", "reason", "sku")}
            if key and key in self.idempotency:
                saved = self.idempotency[key]
                if saved["params"] != params:
                    return HttpResponse(
                        409, {"error": "idempotency_key_reused_with_different_params"}
                    )
                return HttpResponse(
                    200,
                    {**saved["refund"], "idempotent_replayed": True},
                    {"Idempotent-Replayed": "true"},
                )
            payment = self.payments_table.get(str(body.get("payment_id")))
            if payment is None:
                return HttpResponse(404, {"error": "payment_not_found"})
            amount = int(body.get("amount_cents") or 0)
            if amount <= 0:
                return HttpResponse(400, {"error": "invalid_amount"})
            refunded = sum(
                r["amount_cents"] for r in self.refunds if r["payment_id"] == payment["payment_id"]
            )
            if refunded + amount > payment["captured_cents"]:
                return HttpResponse(
                    400,
                    {
                        "error": "amount_exceeds_refundable",
                        "refundable_cents": payment["captured_cents"] - refunded,
                    },
                )
            refund = {
                "id": f"re_{len(self.refunds) + 1:04d}",
                "payment_id": payment["payment_id"],
                "amount_cents": amount,
                "currency": payment["currency"],
                "reason": body.get("reason"),
                "sku": body.get("sku"),
                "status": "succeeded",
                "idempotency_key": key,
                "created_at": self.clock.now().isoformat(),
            }
            self.refunds.append(refund)
            if key:
                self.idempotency[key] = {"params": params, "refund": refund}
            return HttpResponse(201, copy.deepcopy(refund))

        @gw.route("GET", "/v1/refunds")
        def list_refunds(req: HttpRequest) -> HttpResponse:
            pid = req.params.get("payment_id")
            data = [copy.deepcopy(r) for r in self.refunds if r["payment_id"] == pid]
            return HttpResponse(200, {"payment_id": pid, "data": data, "count": len(data)})

    # -- policy helpers -------------------------------------------------------------------
    def eligibility(self, order_id: str, sku: str) -> dict[str, Any]:
        order = self.db.get("orders", order_id)
        item = next((i for i in order["items"] if i["sku"] == sku), None)
        if item is None:
            return {
                "order_id": order_id,
                "sku": sku,
                "eligible": False,
                "reason": "item_not_in_order",
            }
        delivered = datetime.fromisoformat(order["delivered_at"])
        age_days = (self.clock.now() - delivered).days
        already = sum(
            r["amount_cents"]
            for r in self.refunds
            if r["payment_id"] == order["payment_id"] and r.get("sku") == sku
        )
        line_total = item["price_cents"] * item["qty"]
        if age_days > REFUND_WINDOW_DAYS:
            return {
                "order_id": order_id,
                "sku": sku,
                "eligible": False,
                "reason": "outside_window",
                "days_since_delivery": age_days,
            }
        if already >= line_total:
            return {
                "order_id": order_id,
                "sku": sku,
                "eligible": False,
                "reason": "already_refunded",
            }
        return {
            "order_id": order_id,
            "sku": sku,
            "eligible": True,
            "reason": "within_policy",
            "days_since_delivery": age_days,
            "refundable_amount_cents": line_total - already,
            "payment_id": order["payment_id"],
            "policy": f"Damaged items are refundable within {REFUND_WINDOW_DAYS} days of delivery.",
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "payments": {
                "captured": copy.deepcopy(list(self.payments_table.values())),
                "refunds": copy.deepcopy(self.refunds),
                "total_refunded_cents": sum(r["amount_cents"] for r in self.refunds),
            },
            "orders": self.db.snapshot("orders")["orders"],
            "outbox": copy.deepcopy(self.outbox),
        }
