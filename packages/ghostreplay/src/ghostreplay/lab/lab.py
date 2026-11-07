"""Lab: orchestrates record, replay, counterfactual and regression runs for scenarios."""

from __future__ import annotations

import contextlib
import re
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

from ..core.clock import DEFAULT_EPOCH, DeterministicSources, VirtualClock
from ..core.errors import GhostReplayError, ReplayDivergenceError
from ..diff import TraceDiff, diff_executions
from ..models import (
    EventKind,
    EventSource,
    Execution,
    ExecutionMode,
    ExecutionStatus,
    FaultSpec,
    Provenance,
)
from ..mutation import FaultPlan
from ..recorder import EventListener, Recorder, Redactor
from ..regression.cases import RegressionCase, RegressionReport
from ..regression.generate import pytest_source
from ..regression.invariants import evaluate_all
from ..replay import OFFLINE_MODES, Session, offline_guard
from ..runtime import AgentRuntime
from ..storage import SqliteStore
from .scenario import Scenario

CounterfactualMode = Literal["auto", "replay", "branch"]


class DemoStep(BaseModel):
    id: str
    title: str
    narrative: str
    execution_ids: list[str] = Field(default_factory=list)
    verdict: Literal["pass", "fail", "info", "diverged"] = "info"
    # What the story needs this step to show; ``None`` for purely explanatory steps.
    expected: Literal["pass", "fail"] | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def as_expected(self) -> bool:
        return self.expected is None or self.verdict == self.expected


class DemoStory(BaseModel):
    scenario: str
    app: str
    title: str
    steps: list[DemoStep]
    reports: list[RegressionReport]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ok(self) -> bool:
        """True when every step produced the outcome the story depends on."""
        return all(step.as_expected for step in self.steps)


class Lab:
    """Entry point used by apps, the HTTP server, the CLI and generated tests."""

    def __init__(
        self,
        app: str,
        scenarios: Iterable[Scenario],
        store: SqliteStore | None = None,
        *,
        redactor_factory: type[Redactor] = Redactor,
    ) -> None:
        self.app = app
        self.scenarios = {s.id: s for s in scenarios}
        self.store = store or SqliteStore(":memory:")
        self._redactor_factory = redactor_factory

    def scenario(self, scenario_id: str) -> Scenario:
        if scenario_id not in self.scenarios:
            raise ValueError(f"unknown scenario {scenario_id!r} for lab {self.app}")
        return self.scenarios[scenario_id]

    # ------------------------------------------------------------------------------------
    def record(
        self,
        scenario_id: str,
        variant: str,
        *,
        conditions: dict[str, str] | None = None,
        faults: list[FaultSpec] | None = None,
        title: str = "",
        listeners: Iterable[EventListener] = (),
    ) -> Execution:
        """Run the agent live against a fresh simulated environment and record it."""
        scenario = self.scenario(scenario_id)
        return self._execute(
            scenario,
            variant,
            ExecutionMode.RECORD,
            conditions=scenario.resolve_conditions(conditions),
            faults=faults or [],
            title=title,
            listeners=listeners,
        )

    def replay(
        self, execution_id: str, *, listeners: Iterable[EventListener] = (), title: str = ""
    ) -> Execution:
        """Deterministic offline replay: no tool handler or model adapter is invoked."""
        ref = self.store.get(execution_id)
        scenario = self.scenario(ref.scenario)
        return self._execute(
            scenario,
            ref.variant,
            ExecutionMode.REPLAY,
            reference=ref,
            conditions=ref.conditions,
            faults=[],
            title=title or f"Offline replay of {ref.title or ref.id}",
            listeners=listeners,
        )

    def counterfactual(
        self,
        execution_id: str,
        faults: list[FaultSpec],
        *,
        variant: str | None = None,
        mode: CounterfactualMode = "auto",
        title: str = "",
        listeners: Iterable[EventListener] = (),
    ) -> Execution:
        """Re-run a recording with injected faults.

        ``replay`` keeps the run strictly offline and stops at the first divergence. ``branch``
        re-executes against the simulated backend after divergence. ``auto`` picks ``branch``
        when a fault needs a real side effect or a different agent variant is under test.
        """
        ref = self.store.get(execution_id)
        scenario = self.scenario(ref.scenario)
        variant = variant or ref.variant
        if mode == "auto":
            needs_branch = FaultPlan(faults).requires_branch or variant != ref.variant
            exec_mode = (
                ExecutionMode.BRANCH if needs_branch else ExecutionMode.COUNTERFACTUAL_REPLAY
            )
        elif mode == "replay":
            if variant != ref.variant:
                raise ValueError("strict replay cannot test a different agent variant; use branch")
            exec_mode = ExecutionMode.COUNTERFACTUAL_REPLAY
        else:
            exec_mode = ExecutionMode.BRANCH
        if not title:
            kinds = ", ".join(sorted({f.kind.replace("_", " ") for f in faults})) or "no fault"
            title = f"Counterfactual: {kinds} → {variant} agent"
        return self._execute(
            scenario,
            variant,
            exec_mode,
            reference=ref,
            conditions=ref.conditions,
            faults=faults,
            title=title,
            listeners=listeners,
        )

    def diff(self, a_id: str, b_id: str) -> TraceDiff:
        return diff_executions(self.store.get(a_id), self.store.get(b_id))

    # ------------------------------------------------------------------------------------
    def run_case(self, case: RegressionCase) -> RegressionReport:
        """Execute a regression case and evaluate its invariants."""
        scenario = self.scenario(case.scenario)
        notes: list[str] = []
        if case.reference is not None:
            if case.reference.scenario != case.scenario:
                raise ValueError("case reference belongs to a different scenario")
            self.store.save(case.reference)
            mode: CounterfactualMode = "branch" if case.mode in ("branch", "record") else "auto"
            execution = self.counterfactual(
                case.reference.id,
                case.faults,
                variant=case.variant,
                mode=mode,
                title=f"Regression: {case.title}",
            )
        else:
            execution = self.record(
                case.scenario,
                case.variant,
                conditions=case.conditions,
                faults=case.faults,
                title=f"Regression: {case.title}",
            )
        selected = [
            i for i in execution.invariants if case.invariants is None or i.id in case.invariants
        ]
        if case.invariants is not None:
            missing = set(case.invariants) - {i.id for i in selected}
            if missing:
                notes.append(f"unknown invariants ignored: {', '.join(sorted(missing))}")
        passed = bool(selected) and all(i.status == "passed" for i in selected)
        if any(i.status == "inconclusive" for i in selected):
            notes.append("some invariants were inconclusive; they do not count as passed")
        if execution.status == ExecutionStatus.FAILED:
            notes.append("agent crashed during the run")
            passed = False
        del scenario
        return RegressionReport(
            case_id=case.id,
            title=case.title,
            app=case.app,
            scenario=case.scenario,
            variant=case.variant,
            expect=case.expect,
            passed=passed,
            outcome_matches_expectation=passed == (case.expect == "pass"),
            execution_id=execution.id,
            mode=execution.mode.value,
            status=execution.status.value,
            duration_ms=execution.duration_ms,
            invariants=selected,
            divergence=execution.divergence,
            notes=notes,
        )

    def case_from_execution(
        self,
        execution_id: str,
        *,
        variant: str | None = None,
        expect: Literal["pass", "fail"] | None = None,
        case_id: str | None = None,
    ) -> RegressionCase:
        """Turn an execution (usually a counterfactual) into a reproducible regression case."""
        ex = self.store.get(execution_id)
        scenario = self.scenario(ex.scenario)
        if ex.reference_execution_id:
            reference = self.store.get(ex.reference_execution_id)
            faults = ex.faults
        else:  # a plain recording: re-run under the same conditions
            reference, faults = None, ex.faults
        variant = variant or ex.variant
        if expect is None:
            expect = "pass" if scenario.variant(variant).is_fix else "fail"
        preset = "-".join(sorted({f.kind for f in faults})) or "baseline"
        cid = case_id or _slug(f"{scenario.id}-{preset}-{variant}")
        return RegressionCase(
            id=cid,
            title=f"{scenario.title}: {preset.replace('_', ' ')} ({variant})",
            description=(
                f"Generated from execution {ex.id}. Expected {expect.upper()}: "
                f"{'the fix must hold' if expect == 'pass' else 'the detector must catch the bug'}."
            ),
            app=self.app,
            scenario=scenario.id,
            variant=variant,
            conditions=ex.conditions,
            faults=faults,
            reference=reference,
            expect=expect,
            mode="branch" if reference is not None else "record",
        )

    def export_case(self, execution_id: str, **kwargs: Any) -> dict[str, Any]:
        case = self.case_from_execution(execution_id, **kwargs)
        case_file = f"{case.id}.case.json"
        return {
            "case": case.model_dump(mode="json"),
            "case_file": case_file,
            "test_file": f"test_{case.id.replace('-', '_')}.py",
            "pytest_source": pytest_source(case, case_file),
        }

    # ------------------------------------------------------------------------------------
    def prepare_demo(self, scenario_id: str, preset_id: str | None = None) -> DemoStory:
        """Run the full story for a scenario: incident → replay → counterfactual → fix → proof."""
        sc = self.scenario(scenario_id)
        vuln, fixed = sc.vulnerable_variant(), sc.fixed_variant()
        presets = sc.fault_presets()
        preset = (
            sc.preset(preset_id)
            if preset_id
            else next((p for p in presets if p.headline), presets[0])
        )

        incident = self.record(
            sc.id,
            vuln,
            conditions=sc.incident_conditions(),
            title="Incident: recorded production-like run",
        )
        replay = self.replay(incident.id, title="Offline replay of the incident")
        replay_diff = diff_executions(incident, replay)
        baseline = self.record(sc.id, vuln, title="Healthy run (recorded baseline)")
        cf_vuln = self.counterfactual(
            baseline.id,
            preset.faults,
            variant=vuln,
            mode="branch",
            title=f"Counterfactual: {preset.title} → {vuln} agent",
        )
        cf_fixed = self.counterfactual(
            baseline.id,
            preset.faults,
            variant=fixed,
            mode="branch",
            title=f"Counterfactual: {preset.title} → {fixed} agent",
        )
        fix_diff = diff_executions(cf_vuln, cf_fixed)
        reports = [
            self.run_case(self.case_from_execution(cf_vuln.id, variant=vuln)),
            self.run_case(self.case_from_execution(cf_vuln.id, variant=fixed)),
        ]

        def verdict(ex: Execution) -> Literal["pass", "fail"]:
            return "fail" if any(i.status == "failed" for i in ex.invariants) else "pass"

        head = sc.headline_invariant
        steps = [
            DemoStep(
                id="incident",
                expected="fail",
                title="1 · The incident",
                narrative=sc.summary,
                execution_ids=[incident.id],
                verdict=verdict(incident),
                data={"failed": [i.id for i in incident.invariants if i.status == "failed"]},
            ),
            DemoStep(
                id="replay",
                expected="pass",
                title="2 · Reproduce it offline",
                narrative=(
                    "GhostReplay replays the recording without calling a single tool "
                    "or model. Every response comes from the recording, in order."
                ),
                execution_ids=[incident.id, replay.id],
                verdict="pass" if replay_diff.identical else "diverged",
                data={"identical": replay_diff.identical, "diff_entries": len(replay_diff.entries)},
            ),
            DemoStep(
                id="explain",
                title="3 · Why it happened",
                narrative=sc.bug_explanation,
                execution_ids=[incident.id],
                verdict="info",
                data={"headline_invariant": head},
            ),
            DemoStep(
                id="counterfactual",
                expected="fail",
                title="4 · Break a healthy run on purpose",
                narrative=(
                    f"Starting from a healthy recording, the Failure Lab injects "
                    f"'{preset.title}'. {preset.summary}"
                ),
                execution_ids=[baseline.id, cf_vuln.id],
                verdict=verdict(cf_vuln),
                data={"preset": preset.id},
            ),
            DemoStep(
                id="fix",
                expected="pass",
                title="5 · Apply the fix and run the same failure",
                narrative=sc.fix_explanation,
                execution_ids=[cf_vuln.id, cf_fixed.id],
                verdict=verdict(cf_fixed),
                data={"first_divergence": fix_diff.first_divergence},
            ),
            DemoStep(
                id="prove",
                expected="pass",
                title="6 · Prove it with a regression test",
                narrative=(
                    "The scenario becomes a pytest regression case. It FAILS on the "
                    "vulnerable agent and PASSES on the fixed one."
                ),
                execution_ids=[r.execution_id for r in reports],
                verdict="pass" if all(r.outcome_matches_expectation for r in reports) else "fail",
            ),
        ]
        return DemoStory(scenario=sc.id, app=self.app, title=sc.title, steps=steps, reports=reports)

    # ------------------------------------------------------------------------------------
    def _execute(
        self,
        scenario: Scenario,
        variant: str,
        mode: ExecutionMode,
        *,
        reference: Execution | None = None,
        conditions: dict[str, str],
        faults: list[FaultSpec],
        title: str = "",
        listeners: Iterable[EventListener] = (),
    ) -> Execution:
        scenario.variant(variant)  # validate
        start = datetime.fromisoformat(reference.started_at) if reference else DEFAULT_EPOCH
        clock = VirtualClock(start)
        env = scenario.build_environment(conditions, clock)
        offline = mode in OFFLINE_MODES
        model = scenario.build_model()
        agent = scenario.build_agent(variant)
        task = dict(reference.task) if reference else scenario.default_task()
        execution = Execution(
            id=f"{_MODE_PREFIX[mode]}_{uuid.uuid4().hex[:10]}",
            app=self.app,
            scenario=scenario.id,
            variant=variant,
            agent=agent.name,
            mode=mode,
            created_at=datetime.now(UTC).isoformat(),
            started_at=clock.now().isoformat(),
            provenance=Provenance(
                model_provider=model.provider,
                model=model.model,
                model_is_live=model.is_live,
                label=model.label,
                tool_backends="simulated (in-memory)"
                if not offline
                else "none (served from recording)",
            ),
            task=task,
            reference_execution_id=reference.id if reference else None,
            faults=list(faults),
            conditions=dict(conditions),
            title=title,
        )
        recorder = Recorder(
            execution, clock, redactor=self._redactor_factory(), listeners=list(listeners)
        )
        session = Session(recorder, mode=mode, clock=clock, reference=reference, faults=faults)
        rt = AgentRuntime(
            session,
            tools=env.tools.offline_copy() if offline else env.tools,
            model=None if offline else model,
            sources=DeterministicSources(f"{scenario.id}:{variant}:{conditions}"),
            agent_name=agent.name,
        )
        recorder.emit(
            EventKind.EXECUTION_START,
            scenario.id,
            source=EventSource.FRAMEWORK,
            request=task,
            metadata={
                "mode": mode.value,
                "variant": variant,
                "conditions": conditions,
                "faults": [f.id for f in faults],
            },
        )
        if offline:
            assert reference is not None
            snap = next(
                (
                    e
                    for e in reference.events
                    if e.kind == EventKind.STATE_SNAPSHOT and e.name == "initial"
                ),
                None,
            )
            if snap is not None:
                recorder.emit(
                    EventKind.STATE_SNAPSHOT,
                    "initial",
                    source=EventSource.RECORDED,
                    response=snap.response,
                    metadata={"copied_from": snap.event_id},
                )
        else:
            recorder.emit(
                EventKind.STATE_SNAPSHOT,
                "initial",
                source=EventSource.FRAMEWORK,
                response=env.snapshot(),
            )

        t0 = clock.monotonic_ms()
        guard = offline_guard() if offline else contextlib.nullcontext()
        try:
            with guard:
                result = agent.run(rt, task)
            execution.output = result
            execution.status = ExecutionStatus.COMPLETED
        except ReplayDivergenceError:
            execution.status = ExecutionStatus.DIVERGED
        except GhostReplayError as exc:
            execution.status = ExecutionStatus.FAILED
            recorder.emit(
                EventKind.ERROR,
                type(exc).__name__,
                source=EventSource.FRAMEWORK,
                error={"type": type(exc).__name__, "message": str(exc)},
            )
        except Exception as exc:  # agent bug: record it, never hide it
            execution.status = ExecutionStatus.FAILED
            recorder.emit(
                EventKind.ERROR,
                "agent_crash",
                source=EventSource.FRAMEWORK,
                error={"type": type(exc).__name__, "message": str(exc)},
            )

        session.finish()
        if (
            offline
            and session.divergence is not None
            and execution.status != ExecutionStatus.FAILED
        ):
            execution.status = ExecutionStatus.DIVERGED
        execution.divergence = session.divergence

        if not offline:
            final = env.snapshot()
            recorder.emit(
                EventKind.STATE_SNAPSHOT, "final", source=EventSource.FRAMEWORK, response=final
            )
            execution.final_state = recorder.redactor.redact(final)
        elif mode == ExecutionMode.REPLAY and execution.status == ExecutionStatus.COMPLETED:
            assert reference is not None
            execution.final_state = reference.final_state
            snap = next(
                (
                    e
                    for e in reference.events
                    if e.kind == EventKind.STATE_SNAPSHOT and e.name == "final"
                ),
                None,
            )
            if snap is not None:
                recorder.emit(
                    EventKind.STATE_SNAPSHOT,
                    "final",
                    source=EventSource.RECORDED,
                    response=snap.response,
                    metadata={"copied_from": snap.event_id},
                )
        else:
            execution.notes.append(
                "Final state is not observable in an offline counterfactual; invariants that "
                "need it are inconclusive. Use branch mode to execute the continuation."
            )
        if execution.divergence is not None and offline and execution.divergence.after_fault:
            execution.notes.append(
                "The agent's behaviour changed after the injected fault. GhostReplay stopped "
                "instead of inventing a continuation; run the counterfactual in branch mode to "
                "execute it against the simulated backend."
            )
        if mode == ExecutionMode.BRANCH:
            execution.notes.append(
                "Branch execution: tools re-executed against a fresh simulated environment; "
                "events after the first divergence are new executions, not recordings."
            )

        recorder.emit(
            EventKind.EXECUTION_END,
            execution.status.value,
            source=EventSource.FRAMEWORK,
            response=execution.output.model_dump(mode="json") if execution.output else None,
            metadata={"consumed_recorded_interactions": session.consumed},
        )
        execution.duration_ms = round(clock.monotonic_ms() - t0, 3)
        execution.invariants = evaluate_all(scenario.invariants(), execution)
        self.store.save(execution)
        return execution


_MODE_PREFIX = {
    ExecutionMode.RECORD: "rec",
    ExecutionMode.REPLAY: "rpl",
    ExecutionMode.COUNTERFACTUAL_REPLAY: "cfr",
    ExecutionMode.BRANCH: "brn",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80]
