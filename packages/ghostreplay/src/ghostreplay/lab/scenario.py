"""Scenario abstraction: how an application plugs an agent into GhostReplay."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..core.clock import Clock
from ..mocking.model import ModelAdapter
from ..mocking.tools import ToolRegistry
from ..models import AgentResult, FaultPreset
from ..regression.invariants import Invariant
from ..runtime import AgentRuntime


class Agent(Protocol):
    name: str

    def run(self, rt: AgentRuntime, task: dict[str, Any]) -> AgentResult: ...


@dataclass
class Environment:
    """A freshly built simulated world for one execution."""

    tools: ToolRegistry
    snapshot: Callable[[], dict[str, Any]]
    clock: Clock
    backends: dict[str, Any] = field(default_factory=dict)
    #: Called once when the execution ends (stop local services, delete scratch databases).
    close: Callable[[], None] | None = None


@dataclass(frozen=True)
class Variant:
    id: str
    title: str
    description: str
    is_fix: bool = False


@dataclass(frozen=True)
class Condition:
    id: str
    title: str
    options: tuple[str, ...]
    default: str
    incident: str
    description: str = ""


class Scenario(ABC):
    id: str
    app: str
    title: str
    summary: str
    bug_explanation: str
    fix_explanation: str
    variants: tuple[Variant, ...]
    conditions: tuple[Condition, ...] = ()
    headline_invariant: str = ""
    #: What the tools talk to, shown in every execution's provenance.
    tool_backends: str = "simulated (in-memory)"

    @abstractmethod
    def default_task(self) -> dict[str, Any]: ...

    @abstractmethod
    def build_environment(self, conditions: dict[str, str], clock: Clock) -> Environment: ...

    def build_offline_environment(self, conditions: dict[str, str], clock: Clock) -> Environment:
        """Environment for strict offline replay. Only the tool *specifications* are used
        (handlers are replaced by stubs that raise), so scenarios backed by real services or
        databases override this to avoid starting them at all."""
        return self.build_environment(conditions, clock)

    @abstractmethod
    def build_model(self) -> ModelAdapter: ...

    @abstractmethod
    def build_agent(self, variant: str) -> Agent: ...

    @abstractmethod
    def invariants(self) -> list[Invariant]: ...

    def fault_presets(self) -> list[FaultPreset]:
        return []

    # -- helpers ------------------------------------------------------------------------
    def variant(self, variant_id: str) -> Variant:
        for v in self.variants:
            if v.id == variant_id:
                return v
        raise ValueError(f"scenario {self.id} has no variant {variant_id!r}")

    def vulnerable_variant(self) -> str:
        return next(v.id for v in self.variants if not v.is_fix)

    def fixed_variant(self) -> str:
        return next(v.id for v in self.variants if v.is_fix)

    def resolve_conditions(self, overrides: dict[str, str] | None) -> dict[str, str]:
        resolved = {c.id: c.default for c in self.conditions}
        for key, value in (overrides or {}).items():
            cond = next((c for c in self.conditions if c.id == key), None)
            if cond is None:
                raise ValueError(f"unknown condition {key!r} for scenario {self.id}")
            if value not in cond.options:
                raise ValueError(f"condition {key} must be one of {cond.options}, got {value!r}")
            resolved[key] = value
        return resolved

    def incident_conditions(self) -> dict[str, str]:
        return {c.id: c.incident for c in self.conditions}

    def preset(self, preset_id: str) -> FaultPreset:
        for p in self.fault_presets():
            if p.id == preset_id:
                return p
        raise ValueError(f"scenario {self.id} has no fault preset {preset_id!r}")

    def describe(self) -> dict[str, Any]:
        tools_env = self.build_environment({c.id: c.default for c in self.conditions}, _NullClock())
        return {
            "id": self.id,
            "app": self.app,
            "title": self.title,
            "summary": self.summary,
            "bug_explanation": self.bug_explanation,
            "fix_explanation": self.fix_explanation,
            "headline_invariant": self.headline_invariant,
            "variants": [v.__dict__ for v in self.variants],
            "conditions": [{**c.__dict__, "options": list(c.options)} for c in self.conditions],
            "invariants": [i.describe() for i in self.invariants()],
            "fault_presets": [p.model_dump(mode="json") for p in self.fault_presets()],
            "tools": [s.schema() for s in tools_env.tools.specs()],
            "default_task": self.default_task(),
        }


class _NullClock:
    virtual = True

    def now(self):
        from ..core.clock import DEFAULT_EPOCH

        return DEFAULT_EPOCH

    def monotonic_ms(self) -> float:
        return 0.0

    def advance(self, ms: float) -> None:
        return None
