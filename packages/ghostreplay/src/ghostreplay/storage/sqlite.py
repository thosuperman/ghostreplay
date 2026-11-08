"""SQLite persistence for executions."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
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
    body_json TEXT NOT NULL,
    owner TEXT,
    stored_at REAL
);
CREATE INDEX IF NOT EXISTS idx_exec_app_created ON executions(app, created_at);
"""
# Columns added after the first release; older databases are migrated in place.
_ADDED_COLUMNS = {"owner": "TEXT", "stored_at": "REAL"}
_OWNER_INDEX = "CREATE INDEX IF NOT EXISTS idx_exec_owner ON executions(app, owner, created_at)"


#: Owner of shared, read-only executions (genuine captures shipped with a lab). Every
#: session can read them; none can overwrite them; expiry and pruning never delete them.
LIBRARY_OWNER = "__library__"


class OwnershipConflict(ValueError):
    """An execution id already belongs to a different owner and cannot be overwritten."""


class SqliteStore:
    """Thread-safe execution store. Use ``":memory:"`` for tests.

    ``max_executions`` caps how many executions are kept per app; the oldest are pruned on
    save. Public deployments use it to bound disk usage.

    Rows may carry an ``owner`` (an opaque key, e.g. a hashed visitor session). Reads that
    pass ``owner`` see only that owner's rows; ``owner=None`` means "no filter". Owned rows
    older than ``owner_ttl_s`` are deleted, and each owner keeps at most
    ``max_per_owner`` executions per app. :meth:`scoped` returns a view bound to one owner.
    """

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        max_executions: int | None = None,
        max_per_owner: int | None = None,
        owner_ttl_s: float | None = None,
    ) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        self.max_executions = max_executions
        self.max_per_owner = max_per_owner
        self.owner_ttl_s = owner_ttl_s
        self._last_expiry = 0.0
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        self._lock = threading.Lock()
        with self._lock:
            if self.path != ":memory:":
                # WAL keeps readers and the writer from blocking each other and survives
                # crashes mid-write without corrupting committed executions.
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
                self._conn.execute("PRAGMA busy_timeout=10000")
            self._conn.executescript(_SCHEMA)
            have = {r[1] for r in self._conn.execute("PRAGMA table_info(executions)")}
            for column, kind in _ADDED_COLUMNS.items():
                if column not in have:
                    self._conn.execute(f"ALTER TABLE executions ADD COLUMN {column} {kind}")
            self._conn.execute(_OWNER_INDEX)
            self._conn.commit()

    def scoped(self, owner: str) -> OwnedStore:
        """A view of this store that only reads and writes ``owner``'s executions."""
        return OwnedStore(self, owner)

    def save(self, execution: Execution, *, owner: str | None = None) -> None:
        """Insert or update ``execution``.

        An existing row is only replaced when it has the same owner; otherwise
        :class:`OwnershipConflict` is raised, so one visitor can never overwrite another
        visitor's execution by reusing its id.
        """
        summary = execution.summary()
        now = time.time()
        with self._lock, self._conn:  # one transaction: upsert + prune
            cur = self._conn.execute(
                "INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET app=excluded.app, scenario=excluded.scenario,"
                " variant=excluded.variant, mode=excluded.mode, status=excluded.status,"
                " created_at=excluded.created_at, schema_version=excluded.schema_version,"
                " summary_json=excluded.summary_json, body_json=excluded.body_json,"
                " stored_at=excluded.stored_at"
                " WHERE executions.owner IS excluded.owner",
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
                    owner,
                    now,
                ),
            )
            if cur.rowcount == 0:
                raise OwnershipConflict(f"execution id {execution.id!r} is already in use")
            if owner is not None and self.max_per_owner:
                self._conn.execute(
                    "DELETE FROM executions WHERE app = ? AND owner = ? AND id NOT IN ("
                    " SELECT id FROM executions WHERE app = ? AND owner = ?"
                    " ORDER BY created_at DESC, rowid DESC LIMIT ?)",
                    (execution.app, owner, execution.app, owner, self.max_per_owner),
                )
            if self.max_executions:
                self._conn.execute(
                    "DELETE FROM executions WHERE app = ? AND owner IS NOT ? AND id NOT IN ("
                    " SELECT id FROM executions WHERE app = ?"
                    " ORDER BY created_at DESC, rowid DESC LIMIT ?)",
                    (execution.app, LIBRARY_OWNER, execution.app, self.max_executions),
                )
            if self.owner_ttl_s and now - self._last_expiry > 60:
                self._last_expiry = now
                self._conn.execute(
                    "DELETE FROM executions WHERE owner IS NOT NULL AND owner != ? AND stored_at < ?",
                    (LIBRARY_OWNER, now - self.owner_ttl_s),
                )

    def expire(self, *, now: float | None = None) -> int:
        """Delete owned executions older than ``owner_ttl_s``; returns the number removed."""
        if not self.owner_ttl_s:
            return 0
        now = time.time() if now is None else now
        with self._lock, self._conn:
            self._last_expiry = now
            return self._conn.execute(
                "DELETE FROM executions WHERE owner IS NOT NULL AND owner != ? AND stored_at < ?",
                (LIBRARY_OWNER, now - self.owner_ttl_s),
            ).rowcount

    def get(
        self, execution_id: str, *, owner: str | None = None, include_library: bool = True
    ) -> Execution:
        sql, params = "SELECT body_json FROM executions WHERE id = ?", [execution_id]
        if owner is not None:
            sql += " AND (owner = ? OR owner = ?)" if include_library else " AND owner = ?"
            params.extend([owner, LIBRARY_OWNER] if include_library else [owner])
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        if row is None:
            raise ExecutionNotFound(f"execution {execution_id!r} not found")
        return parse_document(Execution, row[0], source=f"stored execution {execution_id!r}")

    def list(
        self,
        *,
        app: str | None = None,
        scenario: str | None = None,
        limit: int = 200,
        owner: str | None = None,
        include_library: bool = True,
    ) -> list[ExecutionSummary]:
        """Summaries, newest first. Unreadable rows are skipped (and logged), not fatal."""
        sql = "SELECT id, summary_json FROM executions WHERE 1=1"
        params: list[object] = []
        if app:
            sql += " AND app = ?"
            params.append(app)
        if owner is not None:
            sql += " AND (owner = ? OR owner = ?)" if include_library else " AND owner = ?"
            params.extend([owner, LIBRARY_OWNER] if include_library else [owner])
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

    def library_ids(self, *, app: str | None = None) -> list[str]:
        sql, params = "SELECT id FROM executions WHERE owner = ?", [LIBRARY_OWNER]
        if app:
            sql += " AND app = ?"
            params.append(app)
        with self._lock:
            return [r[0] for r in self._conn.execute(sql + " ORDER BY created_at", params)]

    def count(self, *, app: str | None = None, owner: str | None = None) -> int:
        sql, params = "SELECT COUNT(*) FROM executions WHERE 1=1", []
        if app:
            sql += " AND app = ?"
            params.append(app)
        if owner is not None:
            sql += " AND owner = ?"
            params.append(owner)
        with self._lock:
            return int(self._conn.execute(sql, params).fetchone()[0])

    def ping(self) -> bool:
        """Cheap health check used by ``/api/health``."""
        with self._lock:
            return self._conn.execute("SELECT 1").fetchone() == (1,)

    def delete_all(self, *, app: str | None = None, owner: str | None = None) -> int:
        sql, params = "DELETE FROM executions WHERE 1=1", []
        if app:
            sql += " AND app = ?"
            params.append(app)
        if owner is not None:
            sql += " AND owner = ?"
            params.append(owner)
        else:  # "clear everything" never removes the shared capture library
            sql += " AND (owner IS NULL OR owner != ?)"
            params.append(LIBRARY_OWNER)
        with self._lock, self._conn:
            return self._conn.execute(sql, params).rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class OwnedStore:
    """A view of a :class:`SqliteStore` restricted to one owner.

    Anything a lab does through this view — reading a reference, saving a replay, listing
    executions — only ever touches rows that belong to ``owner``. Ids of other owners'
    executions behave exactly like ids that do not exist.
    """

    def __init__(self, base: SqliteStore, owner: str) -> None:
        if not owner:
            raise ValueError("owner must be a non-empty string")
        self.base = base
        self.owner = owner

    @property
    def path(self) -> str:
        return self.base.path

    @property
    def max_executions(self) -> int | None:
        return self.base.max_executions

    def save(self, execution: Execution) -> None:
        self.base.save(execution, owner=self.owner)

    def get(self, execution_id: str) -> Execution:
        return self.base.get(execution_id, owner=self.owner)

    def library_ids(self, *, app: str | None = None) -> list[str]:
        return self.base.library_ids(app=app)

    def list(
        self, *, app: str | None = None, scenario: str | None = None, limit: int = 200
    ) -> list[ExecutionSummary]:
        return self.base.list(app=app, scenario=scenario, limit=limit, owner=self.owner)

    def count(self, *, app: str | None = None) -> int:
        return self.base.count(app=app, owner=self.owner)

    def delete_all(self, *, app: str | None = None) -> int:
        return self.base.delete_all(app=app, owner=self.owner)

    def ping(self) -> bool:
        return self.base.ping()
