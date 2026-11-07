"""Canonical JSON, stable hashing and JSON-path helpers.

Replay matching depends on hashing requests the same way during recording and replay, so
everything is normalised to plain JSON types with sorted keys before hashing.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel


def to_jsonable(value: Any) -> Any:
    """Convert ``value`` to plain JSON types (dict/list/str/int/float/bool/None)."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if isinstance(value, BaseModel):
        return to_jsonable(value.model_dump(mode="json"))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return to_jsonable(dataclasses.asdict(value))
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(v) for v in value]
    if isinstance(value, set | frozenset):
        return sorted((to_jsonable(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    raise TypeError(f"Value of type {type(value).__name__} is not JSON-serialisable")


def canonical_json(value: Any) -> str:
    return json.dumps(to_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(*parts: Any, length: int = 16) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(canonical_json(part).encode("utf-8"))
        digest.update(b"\x1f")
    return digest.hexdigest()[:length]


# --------------------------------------------------------------------------------------
# JSON paths: "a.b.0.c" (dot separated, integer segments index lists)
# --------------------------------------------------------------------------------------

_MISSING = object()


def _split(path: str) -> list[str]:
    if not path:
        return []
    return path.split(".")


def get_path(data: Any, path: str, default: Any = None) -> Any:
    current = data
    for seg in _split(path):
        if isinstance(current, dict):
            if seg not in current:
                return default
            current = current[seg]
        elif isinstance(current, list):
            try:
                current = current[int(seg)]
            except (ValueError, IndexError):
                return default
        else:
            return default
    return current


def has_path(data: Any, path: str) -> bool:
    return get_path(data, path, _MISSING) is not _MISSING


def set_path(data: Any, path: str, value: Any) -> Any:
    """Return a deep copy of ``data`` with ``path`` set to ``value``."""
    result = copy.deepcopy(data)
    segs = _split(path)
    if not segs:
        return copy.deepcopy(value)
    current = result
    for seg in segs[:-1]:
        if isinstance(current, list):
            current = current[int(seg)]
        else:
            current = current.setdefault(seg, {})
    last = segs[-1]
    if isinstance(current, list):
        current[int(last)] = copy.deepcopy(value)
    else:
        current[last] = copy.deepcopy(value)
    return result


def delete_path(data: Any, path: str) -> Any:
    """Return a deep copy of ``data`` without ``path`` (no-op if absent)."""
    result = copy.deepcopy(data)
    segs = _split(path)
    if not segs:
        return None
    current = result
    for seg in segs[:-1]:
        current = get_path(current, seg, _MISSING)
        if current is _MISSING:
            return result
    last = segs[-1]
    if isinstance(current, dict):
        current.pop(last, None)
    elif isinstance(current, list):
        try:
            current.pop(int(last))
        except (ValueError, IndexError):
            pass
    return result


def deep_diff(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    """Structural diff of two JSON values as a list of ``{path, op, before, after}``."""
    changes: list[dict[str, Any]] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after), key=str):
            sub = f"{path}.{key}" if path else str(key)
            if key not in before:
                changes.append({"path": sub, "op": "added", "before": None, "after": after[key]})
            elif key not in after:
                changes.append({"path": sub, "op": "removed", "before": before[key], "after": None})
            else:
                changes.extend(deep_diff(before[key], after[key], sub))
        return changes
    if isinstance(before, list) and isinstance(after, list):
        for i in range(max(len(before), len(after))):
            sub = f"{path}.{i}" if path else str(i)
            if i >= len(before):
                changes.append({"path": sub, "op": "added", "before": None, "after": after[i]})
            elif i >= len(after):
                changes.append({"path": sub, "op": "removed", "before": before[i], "after": None})
            else:
                changes.extend(deep_diff(before[i], after[i], sub))
        return changes
    if before != after or type(before) is not type(after):
        if before == after and isinstance(before, int | float) and isinstance(after, int | float):
            return changes
        changes.append({"path": path or "$", "op": "changed", "before": before, "after": after})
    return changes
