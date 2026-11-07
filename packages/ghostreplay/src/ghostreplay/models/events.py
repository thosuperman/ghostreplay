"""Versioned event schema."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "ghostreplay/v1"


class EventKind(StrEnum):
    EXECUTION_START = "execution_start"
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    NONDETERMINISM = "nondeterminism"
    AGENT_STEP = "agent_step"
    GUARD = "guard"
    STATE_SNAPSHOT = "state_snapshot"
    DIVERGENCE = "divergence"
    ERROR = "error"
    EXECUTION_END = "execution_end"


#: Kinds that go through ``Session.interact`` and are matched during replay.
INTERACTION_KINDS = frozenset({EventKind.MODEL_CALL, EventKind.TOOL_CALL, EventKind.NONDETERMINISM})


class EventSource(StrEnum):
    LIVE = "live"  # produced by a real implementation while recording
    RECORDED = "recorded"  # served from a recording during replay
    INJECTED = "injected"  # synthesised or altered by fault injection
    SIMULATED = "simulated"  # re-executed against a simulated backend in branch mode
    FRAMEWORK = "framework"  # bookkeeping produced by GhostReplay itself


class ErrorInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    message: str
    retryable: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class AppliedFault(BaseModel):
    """What fault injection did to an event, including the response it replaced."""

    fault_id: str
    kind: str
    title: str
    strategy: str
    description: str = ""
    operation_executed: bool = False
    original_response: Any = None
    original_error: ErrorInfo | None = None


class ReplayVerdict(StrEnum):
    MATCHED = "matched"  # served from / verified against the recording
    SUBSTITUTED = "substituted"  # recording slot consumed, response replaced by a fault
    DIVERGED = "diverged"  # first mismatching interaction
    LIVE = "live"  # executed after divergence (branch mode only)


class ReplayAnnotation(BaseModel):
    verdict: ReplayVerdict
    recorded_event_id: str | None = None
    recorded_seq: int | None = None
    detail: str = ""


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    execution_id: str
    event_id: str
    parent_event_id: str | None = None
    seq: int
    kind: EventKind
    name: str
    timestamp: str
    duration_ms: float = 0.0
    agent: str | None = None
    source: EventSource
    model: str | None = None
    request: Any = None
    response: Any = None
    error: ErrorInfo | None = None
    state_before: Any = None
    state_after: Any = None
    match_key: str | None = None
    destructive: bool = False
    fault: AppliedFault | None = None
    replay: ReplayAnnotation | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_interaction(self) -> bool:
        return self.kind in INTERACTION_KINDS

    @property
    def succeeded(self) -> bool:
        return self.error is None

    @property
    def committed(self) -> bool:
        """True when the operation's side effect is known to have happened.

        That is the case when it succeeded, or when fault injection executed it and then
        reported an error to the agent (e.g. timeout after commit).
        """
        return self.error is None or (self.fault is not None and self.fault.operation_executed)
