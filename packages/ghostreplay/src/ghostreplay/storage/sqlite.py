"""SQLite persistence for executions."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from ..core.errors import ExecutionNotFound
from ..models import Execution, ExecutionSummary

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
    """Thread-safe execution store. Use ``":memory:"`` for tests."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def save(self, execution: Execution) -> None:
        summary = execution.summary()
        with self._lock:
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
            self._conn.commit()

    def get(self, execution_id: str) -> Execution:
        with self._lock:
            row = self._conn.execute(
                "SELECT body_json FROM executions WHERE id = ?", (execution_id,)
            ).fetchone()
        if row is None:
            raise ExecutionNotFound(f"execution {execution_id!r} not found")
        return Execution.model_validate_json(row[0])

    def list(
        self, *, app: str | None = None, scenario: str | None = None, limit: int = 200
    ) -> list[ExecutionSummary]:
        sql = "SELECT summary_json FROM executions WHERE 1=1"
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
        return [ExecutionSummary.model_validate_json(r[0]) for r in rows]

    def delete_all(self, *, app: str | None = None) -> int:
        with self._lock:
            cur = (
                self._conn.execute("DELETE FROM executions WHERE app = ?", (app,))
                if app
                else self._conn.execute("DELETE FROM executions")
            )
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()
