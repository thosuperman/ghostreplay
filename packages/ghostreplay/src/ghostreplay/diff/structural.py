"""Structural comparison of two executions."""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..core.canonical import deep_diff
from ..models import Event, EventKind, Execution

DiffType = Literal[
    "added_call",
    "removed_call",
    "changed_args",
    "changed_result",
    "changed_error",
    "changed_model_input",
    "changed_model_output",
    "changed_value",
    "added_guard",
    "removed_guard",
]

COMPARED_KINDS = frozenset(
    {EventKind.MODEL_CALL, EventKind.TOOL_CALL, EventKind.NONDETERMINISM, EventKind.GUARD}
)
MAX_CHANGES = 30


class EventRef(BaseModel):
    event_id: str
    seq: int
    kind: str
    name: str
    source: str
    error: str | None = None
    destructive: bool = False
    injected: bool = False


class DiffEntry(BaseModel):
    type: DiffType
    kind: str
    name: str
    summary: str
    a: EventRef | None = None
    b: EventRef | None = None
    changes: list[dict[str, Any]] = Field(default_factory=list)


class AlignedRow(BaseModel):
    index: int
    status: Literal["same", "changed", "added", "removed"]
    a: EventRef | None = None
    b: EventRef | None = None
    entries: list[int] = Field(default_factory=list)


class BehaviorDiff(BaseModel):
    status: tuple[str, str]
    output_status: tuple[str | None, str | None]
    output_message: tuple[str | None, str | None]
    tool_counts: dict[str, tuple[int, int]]
    destructive_calls: tuple[int, int]
    errors: tuple[int, int]
    invariants: list[dict[str, Any]]
    final_state_changes: list[dict[str, Any]]


class TraceDiff(BaseModel):
    a_id: str
    b_id: str
    identical: bool
    first_divergence: dict[str, Any] | None
    rows: list[AlignedRow]
    entries: list[DiffEntry]
    behavior: BehaviorDiff
    counts: dict[str, int]


def _ref(e: Event) -> EventRef:
    return EventRef(
        event_id=e.event_id,
        seq=e.seq,
        kind=e.kind.value,
        name=e.name,
        source=e.source.value,
        error=e.error.type if e.error else None,
        destructive=e.destructive,
        injected=e.fault is not None,
    )


def _sig(e: Event) -> str:
    return f"{e.kind.value}:{e.name}"


def _compare_pair(a: Event, b: Event) -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    kind, name = a.kind.value, a.name
    ra, rb = _ref(a), _ref(b)
    req = deep_diff(a.request, b.request)
    if a.kind == EventKind.GUARD:
        if req:
            entries.append(
                DiffEntry(
                    type="changed_value",
                    kind=kind,
                    name=name,
                    a=ra,
                    b=rb,
                    changes=req[:MAX_CHANGES],
                    summary=f"guard '{name}' details changed",
                )
            )
        return entries
    if req:
        t: DiffType = (
            "changed_model_input"
            if a.kind == EventKind.MODEL_CALL
            else "changed_args"
            if a.kind == EventKind.TOOL_CALL
            else "changed_value"
        )
        entries.append(
            DiffEntry(
                type=t,
                kind=kind,
                name=name,
                a=ra,
                b=rb,
                changes=req[:MAX_CHANGES],
                summary=_summ(t, name, req),
            )
        )
    ea = a.error.model_dump() if a.error else None
    eb = b.error.model_dump() if b.error else None
    if (ea or {}).get("type") != (eb or {}).get("type") or (ea or {}).get("message") != (
        eb or {}
    ).get("message"):
        changes = deep_diff(ea, eb)
        entries.append(
            DiffEntry(
                type="changed_error",
                kind=kind,
                name=name,
                a=ra,
                b=rb,
                changes=changes[:MAX_CHANGES],
                summary=f"{name}: error {ea['type'] if ea else 'none'} → {eb['type'] if eb else 'none'}",
            )
        )
    resp = deep_diff(a.response, b.response)
    if resp:
        t = (
            "changed_model_output"
            if a.kind == EventKind.MODEL_CALL
            else "changed_result"
            if a.kind == EventKind.TOOL_CALL
            else "changed_value"
        )
        entries.append(
            DiffEntry(
                type=t,
                kind=kind,
                name=name,
                a=ra,
                b=rb,
                changes=resp[:MAX_CHANGES],
                summary=_summ(t, name, resp),
            )
        )
    return entries


def _summ(t: str, name: str, changes: list[dict[str, Any]]) -> str:
    label = {
        "changed_args": "arguments changed",
        "changed_result": "result changed",
        "changed_model_input": "model input changed",
        "changed_model_output": "model output changed",
        "changed_value": "value changed",
    }[t]
    paths = ", ".join(c["path"] for c in changes[:3])
    more = f" (+{len(changes) - 3} more)" if len(changes) > 3 else ""
    return f"{name}: {label} at {paths}{more}"


def diff_executions(a: Execution, b: Execution) -> TraceDiff:
    """Align two executions by interaction signature and report structural differences."""
    ea = [e for e in a.events if e.kind in COMPARED_KINDS]
    eb = [e for e in b.events if e.kind in COMPARED_KINDS]
    matcher = SequenceMatcher(a=[_sig(e) for e in ea], b=[_sig(e) for e in eb], autojunk=False)

    rows: list[AlignedRow] = []
    entries: list[DiffEntry] = []

    def add_row(x: Event | None, y: Event | None) -> None:
        row = AlignedRow(
            index=len(rows), status="same", a=_ref(x) if x else None, b=_ref(y) if y else None
        )
        new: list[DiffEntry] = []
        if x is not None and y is not None:
            new = _compare_pair(x, y)
            row.status = "changed" if new else "same"
        elif x is not None:
            row.status = "removed"
            t: DiffType = "removed_guard" if x.kind == EventKind.GUARD else "removed_call"
            new = [
                DiffEntry(
                    type=t,
                    kind=x.kind.value,
                    name=x.name,
                    a=_ref(x),
                    summary=f"{x.name} only in A" + (" (destructive)" if x.destructive else ""),
                )
            ]
        elif y is not None:
            row.status = "added"
            t = "added_guard" if y.kind == EventKind.GUARD else "added_call"
            new = [
                DiffEntry(
                    type=t,
                    kind=y.kind.value,
                    name=y.name,
                    b=_ref(y),
                    summary=f"{y.name} only in B" + (" (destructive)" if y.destructive else ""),
                )
            ]
        for entry in new:
            row.entries.append(len(entries))
            entries.append(entry)
        rows.append(row)

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                add_row(ea[i1 + k], eb[j1 + k])
        elif op == "delete":
            for k in range(i1, i2):
                add_row(ea[k], None)
        elif op == "insert":
            for k in range(j1, j2):
                add_row(None, eb[k])
        else:  # replace
            left, right = ea[i1:i2], eb[j1:j2]
            for k in range(max(len(left), len(right))):
                x = left[k] if k < len(left) else None
                y = right[k] if k < len(right) else None
                if x is not None and y is not None and _sig(x) != _sig(y):
                    add_row(x, None)
                    add_row(None, y)
                else:
                    add_row(x, y)

    first = next((r for r in rows if r.status != "same"), None)
    first_divergence = None
    if first is not None:
        first_divergence = {
            "row": first.index,
            "a_seq": first.a.seq if first.a else None,
            "b_seq": first.b.seq if first.b else None,
            "summary": entries[first.entries[0]].summary if first.entries else first.status,
        }

    behavior = _behavior(a, b)
    counts = Counter(e.type for e in entries)
    identical = (
        not entries
        and behavior.status[0] == behavior.status[1]
        and behavior.output_message[0] == behavior.output_message[1]
    )
    return TraceDiff(
        a_id=a.id,
        b_id=b.id,
        identical=identical,
        first_divergence=first_divergence,
        rows=rows,
        entries=entries,
        behavior=behavior,
        counts=dict(counts),
    )


def _behavior(a: Execution, b: Execution) -> BehaviorDiff:
    def tools(x: Execution) -> Counter[str]:
        return Counter(e.name for e in x.events if e.kind == EventKind.TOOL_CALL)

    ta, tb = tools(a), tools(b)
    names = sorted(set(ta) | set(tb))

    def destructive(x: Execution) -> int:
        return sum(
            1 for e in x.events if e.kind == EventKind.TOOL_CALL and e.destructive and e.committed
        )

    def errors(x: Execution) -> int:
        return sum(1 for e in x.events if e.kind == EventKind.TOOL_CALL and e.error is not None)

    ia = {i.id: i.status for i in a.invariants}
    ib = {i.id: i.status for i in b.invariants}
    inv = [
        {"id": k, "a": ia.get(k), "b": ib.get(k), "changed": ia.get(k) != ib.get(k)}
        for k in sorted(set(ia) | set(ib))
    ]
    state_changes: list[dict[str, Any]] = []
    if a.final_state is not None and b.final_state is not None:
        state_changes = deep_diff(a.final_state, b.final_state)[:50]
    return BehaviorDiff(
        status=(a.status.value, b.status.value),
        output_status=(
            a.output.status if a.output else None,
            b.output.status if b.output else None,
        ),
        output_message=(
            a.output.message if a.output else None,
            b.output.message if b.output else None,
        ),
        tool_counts={n: (ta.get(n, 0), tb.get(n, 0)) for n in names},
        destructive_calls=(destructive(a), destructive(b)),
        errors=(errors(a), errors(b)),
        invariants=inv,
        final_state_changes=state_changes,
    )
