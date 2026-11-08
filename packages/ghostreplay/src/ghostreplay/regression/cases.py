"""Regression cases (data) and reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..models import SCHEMA_VERSION, Divergence, Execution, FaultSpec, InvariantResult
from ..storage.parsing import parse_document

MAX_CASE_BYTES = 20 * 1024 * 1024


class RegressionCase(BaseModel):
    """A reproducible scenario: everything needed to re-run it, and nothing executable."""

    schema_version: str = SCHEMA_VERSION
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_\-]{0,80}$")
    title: str
    description: str = ""
    app: str
    scenario: str
    variant: str
    conditions: dict[str, str] = Field(default_factory=dict)
    task: dict[str, Any] | None = None  # agent input; None = the scenario's default task
    faults: list[FaultSpec] = Field(default_factory=list)
    reference: Execution | None = None
    mode: Literal["auto", "record", "branch"] = "auto"
    invariants: list[str] | None = None  # None = all scenario invariants
    expect: Literal["pass", "fail"] = "pass"


class RegressionReport(BaseModel):
    case_id: str
    title: str
    app: str
    scenario: str
    variant: str
    expect: Literal["pass", "fail"]
    passed: bool  # all selected invariants passed
    outcome_matches_expectation: bool
    execution_id: str
    mode: str
    status: str
    duration_ms: float
    invariants: list[InvariantResult]
    divergence: Divergence | None = None
    notes: list[str] = Field(default_factory=list)

    @property
    def verdict(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def explain(self) -> str:
        lines = [
            f"[{self.verdict}] {self.title} ({self.scenario}/{self.variant}, expected {self.expect.upper()})",
        ]
        for inv in self.invariants:
            mark = {"passed": "✔", "failed": "✘", "inconclusive": "?"}[inv.status]
            lines.append(f"  {mark} {inv.id}: {inv.message}")
            if inv.status == "failed" and inv.explanation:
                lines.append(f"      why it matters: {inv.explanation}")
        if self.divergence:
            lines.append(f"  divergence vs reference: {self.divergence.message}")
        lines.extend(f"  note: {n}" for n in self.notes)
        return "\n".join(lines)


def load_case(path: str | Path) -> RegressionCase:
    """Load and validate a case file. Content is treated purely as data."""
    p = Path(path)
    if p.stat().st_size > MAX_CASE_BYTES:
        raise ValueError(f"case file {p.name} exceeds {MAX_CASE_BYTES} bytes")
    return parse_document(RegressionCase, p.read_bytes(), source=f"case file {p.name}")
