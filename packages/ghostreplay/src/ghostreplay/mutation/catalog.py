"""The fault catalog: what each fault does and whether it needs branch execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Strategy = Literal["error", "transform", "execute_then_error", "delay"]


@dataclass(frozen=True)
class FaultKind:
    id: str
    title: str
    description: str
    strategy: Strategy
    requires_branch: bool
    params: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_KINDS = [
    FaultKind(
        "tool_timeout",
        "Tool timeout (before commit)",
        "The call times out and the operation is NOT performed. The agent cannot tell this "
        "apart from a timeout after commit.",
        "error",
        False,
        {"timeout_ms": "simulated wait before the timeout (default: tool timeout)"},
    ),
    FaultKind(
        "timeout_after_commit",
        "Timeout after commit",
        "The operation really executes against the simulated backend (side effect committed), "
        "then the response is lost and the agent sees a timeout. Needs branch execution because "
        "the simulated world must contain the committed effect.",
        "execute_then_error",
        True,
        {"timeout_ms": "simulated wait before the timeout"},
    ),
    FaultKind(
        "http_429",
        "HTTP 429 rate limited",
        "The service rejects the call with 429.",
        "error",
        False,
        {"retry_after_s": "Retry-After hint"},
    ),
    FaultKind(
        "http_500",
        "HTTP 500 server error",
        "The service fails with 500; nothing is done.",
        "error",
        False,
    ),
    FaultKind(
        "auth_failure", "Authentication failure", "Credentials rejected (401).", "error", False
    ),
    FaultKind(
        "permission_denied", "Permission denied", "Caller lacks permission (403).", "error", False
    ),
    FaultKind(
        "missing_field",
        "Missing response field",
        "A field is removed from the response.",
        "transform",
        False,
        {"path": "dot path, '*' matches every list item"},
    ),
    FaultKind(
        "null_value",
        "Unexpected null",
        "A field in the response is set to null.",
        "transform",
        False,
        {"path": "dot path, '*' matches every list item"},
    ),
    FaultKind(
        "duplicate_response",
        "Duplicate response items",
        "List items in the response are delivered twice (e.g. duplicated records).",
        "transform",
        False,
        {"path": "path of the list (default: first list found)"},
    ),
    FaultKind(
        "reordered_response",
        "Reordered response items",
        "List items in the response arrive in a different order (reversed, or rotated by "
        "'rotate'), exposing agents that depend on the first or last item.",
        "transform",
        False,
        {
            "path": "path of the list (default: first list found)",
            "rotate": "rotate left by N positions instead of reversing",
        },
    ),
    FaultKind(
        "clock_skew",
        "Clock skew",
        "The current time read by the agent (nondeterminism 'clock.now') is shifted by "
        "skew_ms, exposing expiry, refund-window and freshness checks that trust the clock.",
        "transform",
        False,
        {"skew_ms": "milliseconds to add (negative = past)"},
    ),
    FaultKind(
        "stale_data",
        "Stale data",
        "Fields report an older value than the truth (e.g. lagging health view).",
        "transform",
        False,
        {"set": "mapping of dot path -> stale value"},
    ),
    FaultKind(
        "incorrect_output",
        "Incorrect tool output",
        "Fields contain wrong values (misleading tool response).",
        "transform",
        False,
        {"set": "mapping of dot path -> wrong value"},
    ),
    FaultKind(
        "delayed_operation",
        "Delayed operation",
        "The operation executes but takes delay_ms. If that exceeds the tool timeout the "
        "agent sees a timeout although the operation committed.",
        "delay",
        True,
        {"delay_ms": "added latency"},
    ),
    FaultKind(
        "partial_success",
        "Partial success",
        "The operation executes but reports a partial failure to the agent.",
        "execute_then_error",
        True,
        {"message": "error message shown to the agent"},
    ),
]

CATALOG: dict[str, FaultKind] = {k.id: k for k in _KINDS}


def get_kind(kind_id: str) -> FaultKind:
    if kind_id not in CATALOG:
        raise ValueError(f"unknown fault kind {kind_id!r}; known: {', '.join(CATALOG)}")
    return CATALOG[kind_id]
