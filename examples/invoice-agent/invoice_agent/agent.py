"""The invoice agent, instrumented with the public GhostReplay SDK.

Everything GhostReplay records goes through the decorated functions below: one model
function (invoice extraction) and four tools. The tools do real work: SQL queries and writes
against the app's SQLite database and HTTP requests to a local payment service (see
``payments.py``). The buggy agent retries a timed-out payment blindly; the fixed agent uses an
idempotency key and checks the ledger before retrying.

Extraction uses a real LLM (Claude, through the Anthropic SDK) when ``INVOICE_AGENT_LIVE=1``
and ``ANTHROPIC_API_KEY`` are set; otherwise a deterministic parser stands in, and recordings
are labelled accordingly. Either way, replays serve the recorded extraction without calling it.
"""

from __future__ import annotations

import os
import re
from typing import Any

from ghostreplay import GhostReplay, ToolTimeout, TraceView
from ghostreplay.invariants import errors_surfaced

from . import payments

LIVE = os.environ.get("INVOICE_AGENT_LIVE") == "1" and bool(os.environ.get("ANTHROPIC_API_KEY"))
MODEL = os.environ.get("INVOICE_AGENT_MODEL", "claude-opus-5-5")

ghost = GhostReplay(
    "invoice-agent",
    storage=os.environ.get("INVOICE_AGENT_DATA", ".ghostreplay-invoice"),
    title="Invoice Processing Agent",
    description="Extracts an invoice with an LLM, validates it, stores it and pays the vendor once.",
    live_models=LIVE,
    default_task={
        "document": "INVOICE INV-2041\nVendor: ACME-SUPPLY\nAmount due: $129.00\nTerms: NET 30"
    },
)

MAX_ATTEMPTS = 3

_EXTRACT_TOOL = {
    "name": "record_invoice",
    "description": "Record the fields extracted from the invoice document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string", "description": "Invoice number, e.g. INV-2041"},
            "vendor": {"type": "string", "description": "Vendor id exactly as written"},
            "amount_cents": {"type": "integer", "description": "Amount due in cents"},
        },
        "required": ["invoice_id", "vendor", "amount_cents"],
    },
}


# -- the model ----------------------------------------------------------------------------
@ghost.model("invoice-extractor")
def extract_invoice(document: str) -> dict[str, Any]:
    if LIVE:
        import anthropic

        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system="You extract invoice fields. Call record_invoice exactly once.",
            tools=[_EXTRACT_TOOL],
            messages=[{"role": "user", "content": f"Extract the invoice fields:\n\n{document}"}],
        )
        block = next((b for b in msg.content if b.type == "tool_use"), None)
        if block is None:
            return {"error": "the model did not return the invoice fields"}
        return {**dict(block.input), "extracted_by": msg.model}
    number = re.search(r"INVOICE\s+(\S+)", document)
    vendor = re.search(r"Vendor:\s*(\S+)", document)
    amount = re.search(r"Amount due:\s*\$([\d,]+\.\d{2})", document)
    if not (number and vendor and amount):
        return {"error": "could not read the invoice"}
    return {
        "invoice_id": number.group(1),
        "vendor": vendor.group(1),
        "amount_cents": round(float(amount.group(1).replace(",", "")) * 100),
        "extracted_by": "deterministic parser (no LLM)",
    }


# -- the tools (real SQL and HTTP) ------------------------------------------------------------
@ghost.tool("invoices.validate")
def validate_invoice(invoice_id: str, vendor: str, amount_cents: int) -> dict[str, Any]:
    """Check the vendor is approved and the amount is within its purchase-order limit (SQL)."""
    row = payments.world().vendor(vendor)
    limit = row["po_limit_cents"] if row else None
    ok = limit is not None and 0 < amount_cents <= limit
    return {"invoice_id": invoice_id, "approved": ok, "limit_cents": limit}


@ghost.tool("invoices.store")
def store_invoice(invoice_id: str, vendor: str, amount_cents: int) -> dict[str, Any]:
    """Check for an existing record and store the invoice (SQL transaction)."""
    existing = payments.world().find_invoice(invoice_id)
    stored = payments.world().store_invoice(invoice_id, vendor, amount_cents)
    return {**stored, "already_on_file": existing is not None}


@ghost.tool("payments.pay", destructive=True)
def pay(
    invoice_id: str, vendor: str, amount_cents: int, idempotency_key: str | None = None
) -> dict[str, Any]:
    """Request a payment from the local payment service (HTTP POST, commits immediately)."""
    return payments.world().pay(invoice_id, vendor, amount_cents, idempotency_key)


@ghost.tool("payments.list")
def list_payments(invoice_id: str) -> list[dict[str, Any]]:
    """Payments already committed for an invoice (HTTP GET)."""
    return payments.world().payments_for(invoice_id)


@ghost.reset
def _reset() -> None:
    payments.reset()


@ghost.teardown
def _teardown() -> None:
    payments.reset()


@ghost.state
def _state() -> dict[str, Any]:
    return payments.snapshot()


# -- the agents ---------------------------------------------------------------------------
def _prepare(task: dict[str, Any]) -> dict[str, Any] | str:
    invoice = extract_invoice(document=task["document"])
    if "error" in invoice:
        return invoice["error"]
    check = validate_invoice(invoice["invoice_id"], invoice["vendor"], invoice["amount_cents"])
    if not check["approved"]:
        return f"invoice {invoice['invoice_id']} is not approved for payment"
    store_invoice(invoice["invoice_id"], invoice["vendor"], invoice["amount_cents"])
    return invoice


def _paid(invoice: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    dollars = invoice["amount_cents"] / 100
    return {
        "status": "success",
        "message": f"Paid {invoice['invoice_id']} to {invoice['vendor']}: ${dollars:,.2f} "
        f"(payment {receipt['payment_id']}).",
        "payment_id": receipt["payment_id"],
    }


@ghost.agent("buggy", description="Retries a timed-out payment without an idempotency key")
def buggy_agent(task: dict[str, Any]) -> dict[str, Any]:
    invoice = _prepare(task)
    if isinstance(invoice, str):
        return {"status": "refused", "message": invoice}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            receipt = pay(invoice["invoice_id"], invoice["vendor"], invoice["amount_cents"])
            return _paid(invoice, receipt)
        except ToolTimeout:
            # BUG: a timeout does not mean the payment failed. Retrying the same
            # non-idempotent request can pay the vendor twice.
            ghost.step("retry", attempt=attempt, idempotency_key=None)
    return {"status": "failed", "message": "payment service unavailable"}


@ghost.agent("fixed", fix=True, description="Idempotency key + ledger check before retrying")
def fixed_agent(task: dict[str, Any]) -> dict[str, Any]:
    invoice = _prepare(task)
    if isinstance(invoice, str):
        return {"status": "refused", "message": invoice}
    key = f"pay:{invoice['invoice_id']}:{invoice['amount_cents']}"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            receipt = pay(invoice["invoice_id"], invoice["vendor"], invoice["amount_cents"], key)
            return _paid(invoice, receipt)
        except ToolTimeout as exc:
            # The payment may have committed. Look before retrying.
            ghost.step("reconcile", attempt=attempt, idempotency_key=key)
            ledger = list_payments(invoice["invoice_id"])
            committed = [p for p in ledger if p["idempotency_key"] == key]
            if committed:
                ghost.step(
                    "recovered",
                    recovers=getattr(exc, "event_id", None),
                    payment_id=committed[0]["payment_id"],
                )
                return _paid(invoice, committed[0])
    return {"status": "failed", "message": "payment service unavailable"}


# -- safety invariants ----------------------------------------------------------------------
@ghost.invariant(
    "payments.no_duplicate",
    "An invoice is paid at most once",
    severity="critical",
    requires_state=True,
)
def no_duplicate_payment(view: TraceView) -> bool | str:
    by_invoice: dict[str, int] = {}
    for p in (view.final_state or {}).get("payments", []):
        by_invoice[p["invoice_id"]] = by_invoice.get(p["invoice_id"], 0) + 1
    dupes = {k: n for k, n in by_invoice.items() if n > 1}
    if dupes:
        return "; ".join(f"{k} was paid {n} times" for k, n in dupes.items())
    return True


@ghost.invariant(
    "payments.amount_matches_invoice",
    "The vendor receives exactly the invoiced amount",
    severity="critical",
    requires_state=True,
)
def amount_matches(view: TraceView) -> bool | str:
    extracted = [e.response for e in view.model_calls() if isinstance(e.response, dict)]
    invoice = next((r for r in extracted if "amount_cents" in r), None)
    if invoice is None:
        return True
    paid = sum(
        p["amount_cents"]
        for p in (view.final_state or {}).get("payments", [])
        if p["invoice_id"] == invoice["invoice_id"]
    )
    if paid and paid != invoice["amount_cents"]:
        return f"invoiced {invoice['amount_cents']} cents but paid {paid} cents"
    return True


ghost.add_invariant(errors_surfaced(recovery_steps=("recovered",)))
