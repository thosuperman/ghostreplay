"""The capture library: genuine recorded executions shipped with a lab.

Each lab may ship ``*.trace.json`` files (recorded with a live model against its real local
services). ``load_library`` validates them like any untrusted trace and stores them under the
shared, read-only ``LIBRARY_OWNER``: every visitor session can read, replay and re-execute
them; none can modify or delete them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.errors import ExecutionNotFound
from ..models import Execution
from .files import MAX_TRACE_BYTES
from .parsing import parse_document
from .sqlite import LIBRARY_OWNER, SqliteStore


def load_library(store: SqliteStore, directory: str | Path | None) -> list[str]:
    """Load every ``*.trace.json`` in ``directory`` into ``store``. Returns the stored ids."""
    if directory is None or not Path(directory).is_dir():
        return []
    ids: list[str] = []
    for path in sorted(Path(directory).glob("*.trace.json")):
        if path.stat().st_size > MAX_TRACE_BYTES:
            continue
        ex = parse_document(Execution, path.read_bytes(), source=f"library trace {path.name}")
        try:
            store.get(ex.id)
        except ExecutionNotFound:
            store.save(ex, owner=LIBRARY_OWNER)
        ids.append(ex.id)
    return ids


def library_manifest(directory: str | Path | None) -> dict[str, Any]:
    if directory is None:
        return {}
    path = Path(directory) / "MANIFEST.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
