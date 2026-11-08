"""The support agent's world: a real SQLite database and a real HTTP refund service.

Each execution gets a fresh world in a scratch directory:

* ``shop.sqlite3`` — customers, orders, order items, payments, refunds, refund attempts,
  audit events and the outbound reply queue, seeded with fictional TEST DATA;
* a refund service — a real HTTP server on 127.0.0.1 (``ghostreplay.labkit.LocalService``)
  that validates requests, commits refunds in a SQL transaction, honours ``Idempotency-Key``
  headers and keeps a ledger of every attempt.

The agent's tools read the database with SQL and call the refund service over HTTP with a
real socket timeout. Nothing touches a real payment provider and no money moves.

**Controlled fault (incident condition ``payment_gateway=timeout_after_commit``).** The
refund service commits the first refund, then deliberately holds the HTTP response for longer
than the client's timeout. The commit, the timeout, any retry and any duplicate ledger rows
are all real; only the delay is injected, and it is labelled as such.

**Determinism.** Ledger timestamps come from a logical business clock (scenario start + one
second per refund) and ids from the database sequence, so the same decisions produce the same
data and recordings can be re-executed and compared. Wall-clock time is only used for the
network timeout itself.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ghostreplay.core.clock import Clock
from ghostreplay.labkit import LocalService, Request, Response, http_json

REFUND_WINDOW_DAYS = 30
#: Client-side socket timeout for refund requests (real wall-clock milliseconds).
CLIENT_TIMEOUT_MS = int(os.environ.get("GHOSTREPLAY_SUPPORT_CLIENT_TIMEOUT_MS", "1200"))
#: How long the refund service withholds the response after committing, when the fault is on.
COMMIT_DELAY_MS = 2 * CLIENT_TIMEOUT_MS + 300

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE customers (customer_id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL,
    tier TEXT NOT NULL, test_data INTEGER NOT NULL DEFAULT 1);
CREATE TABLE orders (order_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers,
    status TEXT NOT NULL, placed_at TEXT NOT NULL, delivered_at TEXT, currency TEXT NOT NULL,
    payment_id TEXT NOT NULL, total_cents INTEGER NOT NULL, test_data INTEGER NOT NULL DEFAULT 1);
CREATE TABLE order_items (order_id TEXT NOT NULL REFERENCES orders, sku TEXT NOT NULL,
    name TEXT NOT NULL, qty INTEGER NOT NULL, price_cents INTEGER NOT NULL,
    PRIMARY KEY (order_id, sku));
CREATE TABLE payments (payment_id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders,
    captured_cents INTEGER NOT NULL, currency TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE refunds (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
    payment_id TEXT NOT NULL REFERENCES payments, amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    currency TEXT NOT NULL, reason TEXT, sku TEXT, status TEXT NOT NULL,
    idempotency_key TEXT UNIQUE, params_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE refund_attempts (attempt INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id TEXT, amount_cents INTEGER, idempotency_key TEXT, outcome TEXT NOT NULL,
    http_status INTEGER NOT NULL, refund_id TEXT);
CREATE TABLE audit_events (id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL,
    action TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE outbox (id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, ticket_id TEXT NOT NULL,
    message TEXT NOT NULL, channel TEXT NOT NULL);
"""

SEED = """
INSERT INTO customers VALUES ('CUS-0077', 'Maya Chen', 'maya.chen@example.com', 'plus', 1);
INSERT INTO orders VALUES ('ORD-1042', 'CUS-0077', 'delivered', '2026-10-20T14:03:00+00:00',
    '2026-10-24T10:12:00+00:00', 'USD', 'pay_3KQ81', 28800, 1);
INSERT INTO order_items VALUES ('ORD-1042', 'AUR-EB-01', 'Aurora wireless earbuds', 1, 12900);
INSERT INTO order_items VALUES ('ORD-1042', 'LUM-DL-02', 'Lumen desk lamp', 1, 15900);
INSERT INTO payments VALUES ('pay_3KQ81', 'ORD-1042', 28800, 'USD', 'captured');
"""

_REFUND_FIELDS = ("payment_id", "amount_cents", "reason", "sku")


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


class SupportWorld:
    """A fresh shop database plus a running refund service. Call :meth:`close` when done."""

    def __init__(self, clock: Clock, *, payment_gateway: str = "healthy") -> None:
        self.clock = clock
        self.business_start = clock.now()
        self.dir = Path(tempfile.mkdtemp(prefix="ghostreplay-support-"))
        self.db_path = self.dir / "shop.sqlite3"
        self.db = _connect(self.db_path)
        self.db.executescript(SCHEMA)
        self.db.executescript("BEGIN;" + SEED + "COMMIT;")
        self.fault = payment_gateway  # "healthy" | "timeout_after_commit"
        self._delays_left = 1 if payment_gateway == "timeout_after_commit" else 0
        self._lock = threading.Lock()
        self.service = LocalService("refund-service")
        self._routes()
        self.service.start()

    # -- refund service (runs in the service's own threads, own connection) -----------------
    def _routes(self) -> None:
        svc = self.service

        @svc.route("POST", "/v1/refunds")
        def create_refund(req: Request) -> Response:
            body = req.json or {}
            key = req.header("Idempotency-Key")
            params = {k: body.get(k) for k in _REFUND_FIELDS}
            conn = _connect(self.db_path)
            try:
                conn.execute("BEGIN IMMEDIATE")
                if key:
                    row = conn.execute(
                        "SELECT * FROM refunds WHERE idempotency_key = ?", (key,)
                    ).fetchone()
                    if row is not None:
                        if json.loads(row["params_json"]) != params:
                            self._attempt(conn, params, key, "idempotency_conflict", 409, None)
                            conn.execute("COMMIT")
                            return Response(
                                409, {"error": "idempotency_key_reused_with_different_params"}
                            )
                        self._attempt(conn, params, key, "idempotent_replay", 200, row["id"])
                        conn.execute("COMMIT")
                        return Response(
                            200,
                            {**_refund_row(row), "idempotent_replayed": True},
                            {"Idempotent-Replayed": "true"},
                        )
                payment = conn.execute(
                    "SELECT * FROM payments WHERE payment_id = ?", (str(params["payment_id"]),)
                ).fetchone()
                amount = params["amount_cents"]
                if payment is None:
                    self._attempt(conn, params, key, "payment_not_found", 404, None)
                    conn.execute("COMMIT")
                    return Response(404, {"error": "payment_not_found"})
                if not isinstance(amount, int) or amount <= 0:
                    self._attempt(conn, params, key, "invalid_amount", 400, None)
                    conn.execute("COMMIT")
                    return Response(400, {"error": "invalid_amount"})
                refunded = conn.execute(
                    "SELECT COALESCE(SUM(amount_cents), 0) FROM refunds WHERE payment_id = ?",
                    (payment["payment_id"],),
                ).fetchone()[0]
                if refunded + amount > payment["captured_cents"]:
                    self._attempt(conn, params, key, "amount_exceeds_refundable", 400, None)
                    conn.execute("COMMIT")
                    return Response(
                        400,
                        {
                            "error": "amount_exceeds_refundable",
                            "refundable_cents": payment["captured_cents"] - refunded,
                        },
                    )
                n = conn.execute("SELECT COUNT(*) FROM refunds").fetchone()[0] + 1
                refund_id = f"re_{n:04d}"
                created = (self.business_start + timedelta(seconds=n)).isoformat()
                conn.execute(
                    "INSERT INTO refunds (id, payment_id, amount_cents, currency, reason, sku, "
                    "status, idempotency_key, params_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        refund_id,
                        payment["payment_id"],
                        amount,
                        payment["currency"],
                        params["reason"],
                        params["sku"],
                        "succeeded",
                        key,
                        json.dumps(params, sort_keys=True),
                        created,
                    ),
                )
                self._attempt(conn, params, key, "committed", 201, refund_id)
                conn.execute(
                    "INSERT INTO audit_events (actor, action, detail) VALUES (?,?,?)",
                    (
                        "refund-service",
                        "refund.committed",
                        json.dumps(
                            {"refund_id": refund_id, "amount_cents": amount}, sort_keys=True
                        ),
                    ),
                )
                conn.execute("COMMIT")
                row = conn.execute("SELECT * FROM refunds WHERE id = ?", (refund_id,)).fetchone()
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()
            delay = 0.0
            with self._lock:
                if self._delays_left > 0:
                    self._delays_left -= 1
                    delay = COMMIT_DELAY_MS / 1000
            if delay:
                conn = _connect(self.db_path)  # this runs on the service's thread
                try:
                    conn.execute(
                        "INSERT INTO audit_events (actor, action, detail) VALUES (?,?,?)",
                        (
                            "fault-injector",
                            "response.delayed_after_commit",
                            json.dumps(
                                {
                                    "refund_id": refund_id,
                                    "delay_ms": COMMIT_DELAY_MS,
                                    "client_timeout_ms": CLIENT_TIMEOUT_MS,
                                },
                                sort_keys=True,
                            ),
                        ),
                    )
                finally:
                    conn.close()
            return Response(201, _refund_row(row), delay_s=delay)

        @svc.route("GET", "/v1/refunds")
        def list_refunds(req: Request) -> Response:
            pid = req.params.get("payment_id")
            conn = _connect(self.db_path)
            try:
                rows = conn.execute(
                    "SELECT * FROM refunds WHERE payment_id = ? ORDER BY seq", (pid,)
                ).fetchall()
            finally:
                conn.close()
            data = [_refund_row(r) for r in rows]
            return Response(200, {"payment_id": pid, "data": data, "count": len(data)})

    def _attempt(
        self,
        conn: sqlite3.Connection,
        params: dict[str, Any],
        key: str | None,
        outcome: str,
        status: int,
        refund_id: str | None,
    ) -> None:
        conn.execute(
            "INSERT INTO refund_attempts (payment_id, amount_cents, idempotency_key, outcome, "
            "http_status, refund_id) VALUES (?,?,?,?,?,?)",
            (params.get("payment_id"), params.get("amount_cents"), key, outcome, status, refund_id),
        )

    # -- client side (what the agent's tools call) -----------------------------------------
    def post_refund(self, body: dict[str, Any], idempotency_key: str | None = None) -> Any:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        return http_json(
            "POST",
            f"{self.service.url}/v1/refunds",
            service="refund-service",
            json_body=body,
            headers=headers,
            timeout_s=CLIENT_TIMEOUT_MS / 1000,
        )

    def get_refunds(self, payment_id: str) -> Any:
        return http_json(
            "GET",
            f"{self.service.url}/v1/refunds?payment_id={payment_id}",
            service="refund-service",
            timeout_s=CLIENT_TIMEOUT_MS / 1000,
        )

    # -- SQL reads -------------------------------------------------------------------------
    def order(self, order_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if row is None:
            return None
        items = self.db.execute(
            "SELECT sku, name, qty, price_cents FROM order_items WHERE order_id = ? ORDER BY sku",
            (order_id,),
        ).fetchall()
        order = {k: row[k] for k in row.keys() if k != "test_data"}  # noqa: SIM118 (Row iterates values)
        order["items"] = [dict(i) for i in items]
        return order

    def customer(self, customer_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT customer_id, name FROM customers WHERE customer_id = ?", (customer_id,)
        ).fetchone()
        return dict(row) if row else {}

    @property
    def refunds(self) -> list[dict[str, Any]]:
        return [_refund_row(r) for r in self.db.execute("SELECT * FROM refunds ORDER BY seq")]

    def eligibility(self, order_id: str, sku: str) -> dict[str, Any]:
        order = self.order(order_id)
        if order is None:
            return {
                "order_id": order_id,
                "sku": sku,
                "eligible": False,
                "reason": "order_not_found",
            }
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
        already = self.db.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM refunds WHERE payment_id = ? AND sku = ?",
            (order["payment_id"], sku),
        ).fetchone()[0]
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

    def queue_reply(self, customer_id: str, ticket_id: str, message: str) -> dict[str, Any]:
        n = self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] + 1
        msg_id = f"msg_{n:03d}"
        self.db.execute("BEGIN")
        self.db.execute(
            "INSERT INTO outbox VALUES (?,?,?,?,?)",
            (msg_id, customer_id, ticket_id, message, "email (test outbox, never sent)"),
        )
        self.db.execute("COMMIT")
        return {"queued": True, "message_id": msg_id}

    def ledger(self, payment_id: str | None) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT id, amount_cents FROM refunds WHERE payment_id = ? ORDER BY seq", (payment_id,)
        ).fetchall()
        return {
            "payment_id": payment_id,
            "refund_count": len(rows),
            "refunded_cents": sum(r["amount_cents"] for r in rows),
            "refund_ids": [r["id"] for r in rows],
        }

    def snapshot(self) -> dict[str, Any]:
        refunds = self.refunds
        q = self.db.execute
        return {
            "payments": {
                "captured": [dict(r) for r in q("SELECT * FROM payments ORDER BY payment_id")],
                "refunds": refunds,
                "total_refunded_cents": sum(r["amount_cents"] for r in refunds),
            },
            "orders": [self.order(r["order_id"]) for r in q("SELECT order_id FROM orders")],
            "outbox": [dict(r) for r in q("SELECT * FROM outbox ORDER BY id")],
            "refund_attempts": [
                dict(r) for r in q("SELECT * FROM refund_attempts ORDER BY attempt")
            ],
            "audit_events": [
                {**dict(r), "detail": json.loads(r["detail"])}
                for r in q("SELECT * FROM audit_events ORDER BY id")
            ],
            "evidence": {
                "database": "SQLite (fresh per run, fictional TEST DATA)",
                "refund_service": "HTTP on 127.0.0.1",
                "http_requests_received": len(self.service.requests),
                "injected_fault": (
                    f"refund service delays its response {COMMIT_DELAY_MS} ms after committing "
                    f"(client timeout {CLIENT_TIMEOUT_MS} ms)"
                    if self.fault == "timeout_after_commit"
                    else None
                ),
            },
        }

    def close(self) -> None:
        self.service.stop()
        self.db.close()
        shutil.rmtree(self.dir, ignore_errors=True)


def _refund_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "payment_id": row["payment_id"],
        "amount_cents": row["amount_cents"],
        "currency": row["currency"],
        "reason": row["reason"],
        "sku": row["sku"],
        "status": row["status"],
        "idempotency_key": row["idempotency_key"],
        "created_at": row["created_at"],
    }
