"""A tiny deterministic in-memory database for database-like tool operations."""

from __future__ import annotations

import copy
from typing import Any

from ..core.clock import Clock
from ..core.errors import ToolError, register_error_type


@register_error_type
class RecordNotFound(ToolError):
    error_type = "RecordNotFound"


class MockDatabase:
    """Tables of rows keyed by primary key. Reads return deep copies (no aliasing bugs)."""

    def __init__(self, clock: Clock, *, latency_ms: float = 5.0) -> None:
        self.clock = clock
        self.latency_ms = latency_ms
        self._tables: dict[str, dict[str, dict[str, Any]]] = {}
        self.write_log: list[dict[str, Any]] = []

    def create_table(self, name: str, rows: list[dict[str, Any]], *, pk: str = "id") -> None:
        self._tables[name] = {str(r[pk]): copy.deepcopy(r) for r in rows}

    def get(self, table: str, key: str) -> dict[str, Any]:
        self.clock.advance(self.latency_ms)
        row = self._tables.get(table, {}).get(str(key))
        if row is None:
            raise RecordNotFound(f"{table}/{key} not found", data={"table": table, "key": key})
        return copy.deepcopy(row)

    def query(self, table: str, **filters: Any) -> list[dict[str, Any]]:
        self.clock.advance(self.latency_ms)
        rows = self._tables.get(table, {}).values()
        return [copy.deepcopy(r) for r in rows if all(r.get(k) == v for k, v in filters.items())]

    def insert(self, table: str, row: dict[str, Any], *, pk: str = "id") -> dict[str, Any]:
        self.clock.advance(self.latency_ms)
        self._tables.setdefault(table, {})[str(row[pk])] = copy.deepcopy(row)
        self.write_log.append({"op": "insert", "table": table, "key": row[pk]})
        return copy.deepcopy(row)

    def update(self, table: str, key: str, **changes: Any) -> dict[str, Any]:
        self.clock.advance(self.latency_ms)
        row = self._tables.get(table, {}).get(str(key))
        if row is None:
            raise RecordNotFound(f"{table}/{key} not found", data={"table": table, "key": key})
        row.update(copy.deepcopy(changes))
        self.write_log.append({"op": "update", "table": table, "key": key, "changes": changes})
        return copy.deepcopy(row)

    def snapshot(self, *tables: str) -> dict[str, list[dict[str, Any]]]:
        names = tables or tuple(sorted(self._tables))
        return {
            t: [copy.deepcopy(r) for _, r in sorted(self._tables.get(t, {}).items())] for t in names
        }
