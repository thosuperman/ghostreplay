"""Safe file handling for trace import/export."""

from __future__ import annotations

import re
from pathlib import Path

from ..core.errors import UnsafePathError
from ..models import Execution
from .parsing import parse_document

MAX_TRACE_BYTES = 20 * 1024 * 1024
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,120}$")


def safe_join(base: str | Path, name: str) -> Path:
    """Join ``name`` to ``base`` and guarantee the result stays inside ``base``.

    Rejects separators, ``..``, absolute paths and unusual characters outright.
    """
    if not _SAFE_NAME.match(name) or ".." in name:
        raise UnsafePathError(f"unsafe file name: {name!r}")
    base_resolved = Path(base).resolve()
    target = (base_resolved / name).resolve()
    if base_resolved != target.parent:
        raise UnsafePathError(f"{name!r} escapes {base_resolved}")
    return target


def export_execution(execution: Execution, directory: str | Path) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = safe_join(directory, f"{execution.id}.trace.json")
    path.write_text(execution.model_dump_json(indent=2), encoding="utf-8")
    return path


def import_execution(directory: str | Path, name: str) -> Execution:
    """Load a trace file from ``directory``. The content is validated data, never executed."""
    path = safe_join(directory, name)
    if path.stat().st_size > MAX_TRACE_BYTES:
        raise ValueError(f"trace {name} is larger than {MAX_TRACE_BYTES} bytes")
    return parse_document(Execution, path.read_bytes(), source=f"trace file {name}")
