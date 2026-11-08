"""A simulated vendor-payment service (in memory; nothing real is ever paid).

It behaves like a typical payments API: ``pay`` commits a payment and returns a receipt,
and an optional idempotency key makes retries return the original payment instead of
paying twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Approved vendors and the purchase-order limit for each (cents).
VENDORS = {"ACME-SUPPLY": 50_000, "NORTHWIND": 200_000}


@dataclass
class PaymentLedger:
    payments: list[dict[str, Any]] = field(default_factory=list)

    def reset(self) -> None:
        self.payments.clear()

    def pay(
        self, invoice_id: str, vendor: str, amount_cents: int, idempotency_key: str | None
    ) -> dict[str, Any]:
        if idempotency_key:
            for p in self.payments:
                if p["idempotency_key"] == idempotency_key:
                    return {**p, "replayed_by_idempotency_key": True}
        payment = {
            "payment_id": f"pmt_{len(self.payments) + 1:04d}",
            "invoice_id": invoice_id,
            "vendor": vendor,
            "amount_cents": amount_cents,
            "idempotency_key": idempotency_key,
            "status": "settled",
        }
        self.payments.append(payment)
        return dict(payment)

    def for_invoice(self, invoice_id: str) -> list[dict[str, Any]]:
        return [dict(p) for p in self.payments if p["invoice_id"] == invoice_id]

    def snapshot(self) -> dict[str, Any]:
        return {
            "payments": [dict(p) for p in self.payments],
            "total_paid_cents": sum(p["amount_cents"] for p in self.payments),
        }


LEDGER = PaymentLedger()
