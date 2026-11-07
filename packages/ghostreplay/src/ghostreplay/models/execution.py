"""Execution schema and result models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .events import SCHEMA_VERSION, Event, EventKind
from .faults import FaultSpec


class ExecutionMode(StrEnum):
    RECORD = "record"  # live execution (against simulated or real backends) being recorded
    REPLAY = "replay"  # deterministic offline replay of a recording
    COUNTERFACTUAL_REPLAY = "counterfactual-replay"  # offline replay with injected faults
    BRANCH = "branch"  # replay prefix, then re-execution against simulated backends


class ExecutionStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"  # agent finished (regardless of invariant outcome)
    FAILED = "failed"  # agent raised an unexpected exception
    DIVERGED = "diverged"  # offline replay stopped because behaviour diverged


class Provenance(BaseModel):
    """How the decisions in this execution were produced. Shown in every UI."""

    model_provider: str  # "scripted", "anthropic", ...
    model: str
    model_is_live: bool
    label: str
    tool_backends: str = "simulated"


class AgentResult(BaseModel):
    status: Literal["success", "failed", "escalated", "partial", "refused"]
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class InvariantResult(BaseModel):
    id: str
    title: str
    status: Literal["passed", "failed", "inconclusive"]
    severity: Literal["critical", "high", "medium", "low"] = "high"
    message: str
    explanation: str = ""
    evidence: list[str] = Field(default_factory=list)  # event ids

    @property
    def passed(self) -> bool:
        return self.status == "passed"


class Divergence(BaseModel):
    type: Literal["mismatch", "unexpected_call", "incomplete", "result_mismatch"]
    at_seq: int | None = None
    recorded_seq: int | None = None
    expected: dict[str, Any] | None = None
    actual: dict[str, Any] | None = None
    changes: list[dict[str, Any]] = Field(default_factory=list)
    message: str
    after_fault: bool = False


class Execution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    id: str
    app: str
    scenario: str
    variant: str
    agent: str
    mode: ExecutionMode
    status: ExecutionStatus = ExecutionStatus.RUNNING
    created_at: str
    started_at: str
    duration_ms: float = 0.0
    provenance: Provenance
    task: dict[str, Any] = Field(default_factory=dict)
    output: AgentResult | None = None
    reference_execution_id: str | None = None
    faults: list[FaultSpec] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)
    events: list[Event] = Field(default_factory=list)
    final_state: dict[str, Any] | None = None
    invariants: list[InvariantResult] = Field(default_factory=list)
    divergence: Divergence | None = None
    notes: list[str] = Field(default_factory=list)
    title: str = ""

    def interactions(self) -> list[Event]:
        return [e for e in self.events if e.is_interaction]

    def summary(self) -> ExecutionSummary:
        tool_events = [e for e in self.events if e.kind == EventKind.TOOL_CALL]
        failed = [i for i in self.invariants if i.status == "failed"]
        return ExecutionSummary(
            id=self.id,
            app=self.app,
            scenario=self.scenario,
            variant=self.variant,
            mode=self.mode,
            status=self.status,
            created_at=self.created_at,
            duration_ms=self.duration_ms,
            title=self.title,
            tool_calls=len(tool_events),
            model_calls=sum(1 for e in self.events if e.kind == EventKind.MODEL_CALL),
            errors=sum(1 for e in tool_events if e.error is not None),
            destructive_calls=sum(1 for e in tool_events if e.destructive and e.committed),
            injected_faults=sum(1 for e in self.events if e.fault is not None),
            invariants_failed=len(failed),
            invariants_total=len(self.invariants),
            failed_invariants=[i.id for i in failed],
            reference_execution_id=self.reference_execution_id,
            diverged=self.divergence is not None,
            model_provider=self.provenance.model_provider,
            output_status=self.output.status if self.output else None,
        )


class ExecutionSummary(BaseModel):
    id: str
    app: str
    scenario: str
    variant: str
    mode: ExecutionMode
    status: ExecutionStatus
    created_at: str
    duration_ms: float
    title: str
    tool_calls: int
    model_calls: int
    errors: int
    destructive_calls: int
    injected_faults: int
    invariants_failed: int
    invariants_total: int
    failed_invariants: list[str]
    reference_execution_id: str | None
    diverged: bool
    model_provider: str
    output_status: str | None

    @property
    def verdict(self) -> str:
        return "fail" if self.invariants_failed else "pass"
