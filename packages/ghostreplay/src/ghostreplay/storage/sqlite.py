"""SQLite persistence for executions."""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from ..core.errors import ExecutionNotFound, TraceFormatError
from ..models import Execution, ExecutionSummary
from .parsing import parse_document

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,
    app TEXT NOT NULL,
    scenario TEXT NOT NULL,
    variant TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    body_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_exec_app_created ON executions(app, created_at);
"""


class SqliteStore:
    """Thread-safe execution store. Use ``":memory:"`` for tests.

    ``max_executions`` caps how many executions are kept per app; the oldest are pruned on
    save. Public deployments use it to bound disk usage.
    """

    def __init__(self, path: str | Path = ":memory:", *, max_executions: int | None = None) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        self.max_executions = max_executions
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        self._lock = threading.Lock()
        with self._lock:
            if self.path != ":memory:":
                # WAL keeps readers and the writer from blocking each other and survives
                # crashes mid-write without corrupting committed executions.
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def save(self, execution: Execution) -> None:
        summary = execution.summary()
        with self._lock, self._conn:  # one transaction: insert + prune
            self._conn.execute(
                "INSERT OR REPLACE INTO executions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    execution.id,
                    execution.app,
                    execution.scenario,
                    execution.variant,
                    execution.mode.value,
                    execution.status.value,
                    execution.created_at,
                    execution.schema_version,
                    summary.model_dump_json(),
                    execution.model_dump_json(),
                ),
            )
            if self.max_executions:
                self._conn.execute(
                    "DELETE FROM executions WHERE app = ? AND id NOT IN ("
                    " SELECT id FROM executions WHERE app = ?"
                    " ORDER BY created_at DESC, rowid DESC LIMIT ?)",
                    (execution.app, execution.app, self.max_executions),
                )

    def get(self, execution_id: str) -> Execution:
        with self._lock:
            row = self._conn.execute(
                "SELECT body_json FROM executions WHERE id = ?", (execution_id,)
            ).fetchone()
        if row is None:
            raise ExecutionNotFound(f"execution {execution_id!r} not found")
        return parse_document(Execution, row[0], source=f"stored execution {execution_id!r}")

    def list(
        self, *, app: str | None = None, scenario: str | None = None, limit: int = 200
    ) -> list[ExecutionSummary]:
        """Summaries, newest first. Unreadable rows are skipped (and logged), not fatal."""
        sql = "SELECT id, summary_json FROM executions WHERE 1=1"
        params: list[object] = []
        if app:
            sql += " AND app = ?"
            params.append(app)
        if scenario:
            sql += " AND scenario = ?"
            params.append(scenario)
        sql += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params.append(max(1, min(limit, 1000)))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        out: list[ExecutionSummary] = []
        for execution_id, raw in rows:
            try:
                out.append(
                    parse_document(ExecutionSummary, raw, source=f"summary of {execution_id!r}")
                )
            except TraceFormatError as exc:
                log.warning("skipping unreadable execution row: %s", exc)
        return out

    def count(self, *, app: str | None = None) -> int:
        with self._lock:
            sql, params = "SELECT COUNT(*) FROM executions", ()
            if app:
                sql, params = sql + " WHERE app = ?", (app,)
            return int(self._conn.execute(sql, params).fetchone()[0])

    def ping(self) -> bool:
        """Cheap health check used by ``/api/health``."""
        with self._lock:
            return self._conn.execute("SELECT 1").fetchone() == (1,)

    def delete_all(self, *, app: str | None = None) -> int:
        with self._lock, self._conn:
            cur = (
                self._conn.execute("DELETE FROM executions WHERE app = ?", (app,))
                if app
                else self._conn.execute("DELETE FROM executions")
            )
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()
