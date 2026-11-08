"""The invoice app's world: a real SQLite database and a real local HTTP payment service.

* ``invoices.sqlite3`` holds approved vendors (with purchase-order limits), stored invoices and
  the payment ledger. All records are fictional TEST DATA.
* The payment service is a real HTTP server on 127.0.0.1 (``ghostreplay.labkit``). ``POST
  /v1/payments`` validates the request, commits the payment in a SQL transaction and honours an
  ``Idempotency-Key`` header; ``GET /v1/payments?invoice_id=`` lists committed payments.

Nothing contacts a real payment provider. The world is created lazily on the first real tool
call of a run, so a strict offline replay (where no tool runs) never creates one.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ghostreplay.labkit import LocalService, Request, Response, http_json

#: Business clock for ledger timestamps (deterministic, so runs can be compared).
BUSINESS_START = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
CLIENT_TIMEOUT_S = 5.0

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE vendors (vendor_id TEXT PRIMARY KEY, name TEXT NOT NULL,
    po_limit_cents INTEGER NOT NULL, test_data INTEGER NOT NULL DEFAULT 1);
CREATE TABLE invoices (invoice_id TEXT PRIMARY KEY, vendor_id TEXT NOT NULL REFERENCES vendors,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0), status TEXT NOT NULL);
CREATE TABLE payments (seq INTEGER PRIMARY KEY AUTOINCREMENT, payment_id TEXT UNIQUE NOT NULL,
    invoice_id TEXT NOT NULL, vendor TEXT NOT NULL, amount_cents INTEGER NOT NULL,
    idempotency_key TEXT UNIQUE, status TEXT NOT NULL, created_at TEXT NOT NULL);
INSERT INTO vendors VALUES ('ACME-SUPPLY', 'Acme Supply Co. (test)', 50000, 1);
INSERT INTO vendors VALUES ('NORTHWIND', 'Northwind Traders (test)', 200000, 1);
"""


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


class InvoiceWorld:
    def __init__(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="invoice-agent-"))
        self.db_path = self.dir / "invoices.sqlite3"
        self.db = _connect(self.db_path)
        self.db.executescript(SCHEMA)
        self.service = LocalService("payment-service")

        @self.service.route("POST", "/v1/payments")
        def pay(req: Request) -> Response:
            body = req.json or {}
            key = req.header("Idempotency-Key")
            conn = _connect(self.db_path)
            try:
                conn.execute("BEGIN IMMEDIATE")
                if key:
                    row = conn.execute(
                        "SELECT * FROM payments WHERE idempotency_key = ?", (key,)
                    ).fetchone()
                    if row is not None:
                        conn.execute("COMMIT")
                        return Response(200, {**_row(row), "replayed_by_idempotency_key": True})
                amount = body.get("amount_cents")
                if not isinstance(amount, int) or amount <= 0:
                    conn.execute("ROLLBACK")
                    return Response(400, {"error": "invalid_amount"})
                n = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0] + 1
                payment_id = f"pmt_{n:04d}"
                conn.execute(
                    "INSERT INTO payments (payment_id, invoice_id, vendor, amount_cents, "
                    "idempotency_key, status, created_at) VALUES (?,?,?,?,?,?,?)",
                    (
                        payment_id,
                        body.get("invoice_id"),
                        body.get("vendor"),
                        amount,
                        key,
                        "settled",
                        (BUSINESS_START + timedelta(seconds=n)).isoformat(),
                    ),
                )
                conn.execute("COMMIT")
                row = conn.execute(
                    "SELECT * FROM payments WHERE payment_id = ?", (payment_id,)
                ).fetchone()
            finally:
                conn.close()
            return Response(201, _row(row))

        @self.service.route("GET", "/v1/payments")
        def list_payments(req: Request) -> Response:
            conn = _connect(self.db_path)
            try:
                rows = conn.execute(
                    "SELECT * FROM payments WHERE invoice_id = ? ORDER BY seq",
                    (req.params.get("invoice_id"),),
                ).fetchall()
            finally:
                conn.close()
            return Response(200, [_row(r) for r in rows])

        self.service.start()

    # -- client side ---------------------------------------------------------------------------
    def pay(
        self, invoice_id: str, vendor: str, amount_cents: int, key: str | None
    ) -> dict[str, Any]:
        return http_json(
            "POST",
            f"{self.service.url}/v1/payments",
            service="payment-service",
            json_body={"invoice_id": invoice_id, "vendor": vendor, "amount_cents": amount_cents},
            headers={"Idempotency-Key": key} if key else {},
            timeout_s=CLIENT_TIMEOUT_S,
        )

    def payments_for(self, invoice_id: str) -> list[dict[str, Any]]:
        return http_json(
            "GET",
            f"{self.service.url}/v1/payments?invoice_id={invoice_id}",
            service="payment-service",
            timeout_s=CLIENT_TIMEOUT_S,
        )

    # -- SQL ----------------------------------------------------------------------------------
    def vendor(self, vendor_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM vendors WHERE vendor_id = ?", (vendor_id,)).fetchone()
        return dict(row) if row else None

    def find_invoice(self, invoice_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM invoices WHERE invoice_id = ?", (invoice_id,)
        ).fetchone()
        return dict(row) if row else None

    def store_invoice(self, invoice_id: str, vendor: str, amount_cents: int) -> dict[str, Any]:
        self.db.execute("BEGIN")
        self.db.execute(
            "INSERT INTO invoices VALUES (?,?,?,?) ON CONFLICT(invoice_id) DO NOTHING",
            (invoice_id, vendor, amount_cents, "approved"),
        )
        self.db.execute("COMMIT")
        return self.find_invoice(invoice_id) or {}

    def snapshot(self) -> dict[str, Any]:
        payments = [_row(r) for r in self.db.execute("SELECT * FROM payments ORDER BY seq")]
        return {
            "invoices": [
                dict(r) for r in self.db.execute("SELECT * FROM invoices ORDER BY invoice_id")
            ],
            "payments": payments,
            "total_paid_cents": sum(p["amount_cents"] for p in payments),
            "http_requests_received": len(self.service.requests),
        }

    def close(self) -> None:
        self.service.stop()
        self.db.close()
        shutil.rmtree(self.dir, ignore_errors=True)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        k: row[k]
        for k in (
            "payment_id",
            "invoice_id",
            "vendor",
            "amount_cents",
            "idempotency_key",
            "status",
            "created_at",
        )
    }


_world: InvoiceWorld | None = None


def world() -> InvoiceWorld:
    """The current run's world, created on first real use."""
    global _world
    if _world is None:
        _world = InvoiceWorld()
    return _world


def reset() -> None:
    """Discard the previous run's world (the next real tool call creates a fresh one)."""
    global _world
    if _world is not None:
        _world.close()
        _world = None


def snapshot() -> dict[str, Any]:
    return (
        _world.snapshot()
        if _world is not None
        else {"invoices": [], "payments": [], "total_paid_cents": 0}
    )


__all__ = ["InvoiceWorld", "reset", "snapshot", "world"]
