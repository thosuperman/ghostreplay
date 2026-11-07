"""Fault matching and application."""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..core.canonical import delete_path, get_path, set_path, to_jsonable
from ..core.clock import Clock
from ..core.errors import (
    AuthError,
    HttpError,
    PartialFailure,
    PermissionDenied,
    RateLimited,
    ToolError,
    ToolTimeout,
)
from ..models import AppliedFault, ErrorInfo, FaultSpec
from .catalog import get_kind


class FaultPlan:
    """A validated list of faults with occurrence-based matching."""

    def __init__(self, faults: list[FaultSpec] | None = None) -> None:
        self.faults = list(faults or [])
        for f in self.faults:
            get_kind(f.kind)  # validate early

    @property
    def requires_branch(self) -> bool:
        return any(get_kind(f.kind).requires_branch for f in self.faults)

    def match(self, kind: str, name: str, request: Any, occurrence: int) -> FaultSpec | None:
        for fault in self.faults:
            t = fault.target
            if t.kind != kind or t.name != name:
                continue
            if t.occurrence is not None and t.occurrence != occurrence:
                continue
            if t.where and not _contains(request, t.where):
                continue
            return fault
        return None


def _contains(request: Any, where: dict[str, Any]) -> bool:
    if not isinstance(request, dict):
        return False
    return all(get_path(request, k) == v for k, v in where.items())


# ---------------------------------------------------------------------------------------
# Path expansion with '*' wildcard over lists
# ---------------------------------------------------------------------------------------


def expand_paths(data: Any, path: str) -> list[str]:
    segs = path.split(".") if path else []
    results: list[str] = []

    def walk(node: Any, i: int, prefix: list[str]) -> None:
        if i == len(segs):
            results.append(".".join(prefix))
            return
        seg = segs[i]
        if seg == "*":
            if isinstance(node, list):
                for idx, item in enumerate(node):
                    walk(item, i + 1, [*prefix, str(idx)])
            elif isinstance(node, dict):
                for key in node:
                    walk(node[key], i + 1, [*prefix, str(key)])
            return
        if isinstance(node, dict) and seg in node:
            walk(node[seg], i + 1, [*prefix, seg])
        elif isinstance(node, list):
            try:
                walk(node[int(seg)], i + 1, [*prefix, seg])
            except (ValueError, IndexError):
                return
        elif i == len(segs) - 1 and isinstance(node, dict):
            results.append(".".join([*prefix, seg]))  # setting a new leaf key

    walk(data, 0, [])
    return results


def _first_list_path(data: Any, prefix: str = "") -> str | None:
    if isinstance(data, list):
        return prefix
    if isinstance(data, dict):
        for k, v in data.items():
            sub = f"{prefix}.{k}" if prefix else str(k)
            found = _first_list_path(v, sub)
            if found is not None:
                return found
    return None


# ---------------------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------------------


@dataclass
class FaultOutcome:
    response: Any
    error: ToolError | None
    applied: AppliedFault


def _err_info(err: ToolError | None) -> ErrorInfo | None:
    return ErrorInfo(**err.to_info()) if err else None


def apply_fault(
    fault: FaultSpec,
    *,
    op_name: str,
    clock: Clock,
    timeout_ms: float | None,
    baseline: Callable[[], Any],
    execute: Callable[[], Any] | None,
    recorded_response: Any = None,
    recorded_error: ErrorInfo | None = None,
) -> FaultOutcome:
    """Apply ``fault`` to one interaction.

    ``baseline`` returns the unfaulted response (recorded during offline replay, otherwise a
    real execution against the simulated backend). ``execute`` performs the operation against
    the simulated backend and is ``None`` when the session is offline — faults that need it
    (``requires_branch``) are rejected in that case rather than faked.
    """
    kind = get_kind(fault.kind)
    params = fault.params
    applied = AppliedFault(
        fault_id=fault.id,
        kind=kind.id,
        title=kind.title,
        strategy=kind.strategy,
        description=fault.description or kind.description,
        original_response=recorded_response,
        original_error=recorded_error,
    )
    if kind.requires_branch and execute is None:
        raise ValueError(
            f"fault {fault.id} ({kind.id}) requires branch execution; it cannot be applied "
            "during offline replay"
        )

    if kind.strategy == "error":
        wait = (
            float(params.get("timeout_ms") or timeout_ms or 30_000)
            if kind.id == "tool_timeout"
            else 50.0
        )
        clock.advance(wait)
        return FaultOutcome(None, _make_error(kind.id, op_name, params, wait), applied)

    if kind.strategy == "execute_then_error":
        assert execute is not None
        try:
            real = execute()
        except ToolError as exc:  # the operation itself failed; report that faithfully
            applied.operation_executed = True
            applied.original_error = _err_info(exc)
            applied.description += " (operation itself failed; fault had no additional effect)"
            return FaultOutcome(None, exc, applied)
        applied.operation_executed = True
        applied.original_response = to_jsonable(real)
        if kind.id == "timeout_after_commit":
            wait = float(params.get("timeout_ms") or timeout_ms or 30_000)
            clock.advance(wait)
            err: ToolError = ToolTimeout(
                f"{op_name} timed out after {wait:.0f} ms (no response received)",
                data={"timeout_ms": wait},
            )
        else:
            err = PartialFailure(
                str(params.get("message") or f"{op_name} partially failed"),
                data={"partial": True},
            )
        return FaultOutcome(None, err, applied)

    if kind.strategy == "delay":
        assert execute is not None
        delay = float(params.get("delay_ms", 5_000))
        clock.advance(delay)
        real = execute()
        applied.operation_executed = True
        applied.original_response = to_jsonable(real)
        if timeout_ms is not None and delay >= timeout_ms:
            return FaultOutcome(
                None,
                ToolTimeout(
                    f"{op_name} exceeded its {timeout_ms:.0f} ms timeout",
                    data={"timeout_ms": timeout_ms},
                ),
                applied,
            )
        return FaultOutcome(real, None, applied)

    # transform
    try:
        original = to_jsonable(baseline())
    except ToolError as exc:
        applied.original_error = _err_info(exc)
        applied.description += " (baseline call failed; nothing to transform)"
        return FaultOutcome(None, exc, applied)
    applied.original_response = copy.deepcopy(original)
    applied.operation_executed = execute is not None
    mutated, note = _transform(kind.id, original, params)
    if note:
        applied.description += f" ({note})"
    return FaultOutcome(mutated, None, applied)


def _make_error(kind_id: str, op_name: str, params: dict[str, Any], wait: float) -> ToolError:
    if kind_id == "tool_timeout":
        return ToolTimeout(f"{op_name} timed out after {wait:.0f} ms", data={"timeout_ms": wait})
    if kind_id == "http_429":
        return RateLimited(
            f"{op_name}: HTTP 429 Too Many Requests",
            data={"status": 429, "retry_after_s": params.get("retry_after_s", 2)},
        )
    if kind_id == "http_500":
        return HttpError(
            f"{op_name}: HTTP 500 Internal Server Error", retryable=True, data={"status": 500}
        )
    if kind_id == "auth_failure":
        return AuthError(f"{op_name}: HTTP 401 credentials rejected", data={"status": 401})
    if kind_id == "permission_denied":
        return PermissionDenied(
            str(params.get("message") or f"{op_name}: HTTP 403 access denied"),
            data={"status": 403},
        )
    raise ValueError(kind_id)


def _transform(kind_id: str, data: Any, params: dict[str, Any]) -> tuple[Any, str]:
    if kind_id in ("missing_field", "null_value"):
        path = str(params.get("path", ""))
        paths = [
            p for p in expand_paths(data, path) if get_path(data, p, _SENTINEL) is not _SENTINEL
        ]
        if not paths:
            return data, f"path '{path}' not present; response unchanged"
        for p in paths:
            data = delete_path(data, p) if kind_id == "missing_field" else set_path(data, p, None)
        return data, ""
    if kind_id in ("stale_data", "incorrect_output"):
        changes = params.get("set") or {}
        if not isinstance(changes, dict) or not changes:
            return data, "no 'set' mapping given; response unchanged"
        for path, value in changes.items():
            for p in expand_paths(data, str(path)):
                data = set_path(data, p, value)
        return data, ""
    if kind_id == "duplicate_response":
        path = params.get("path")
        path = str(path) if path is not None else _first_list_path(data)
        if path is None:
            return data, "no list in response; response unchanged"
        items = get_path(data, path) if path else data
        if not isinstance(items, list):
            return data, f"'{path}' is not a list; response unchanged"
        doubled = [copy.deepcopy(i) for i in items for _ in range(2)]
        return (set_path(data, path, doubled) if path else doubled), ""
    raise ValueError(kind_id)


_SENTINEL = object()
