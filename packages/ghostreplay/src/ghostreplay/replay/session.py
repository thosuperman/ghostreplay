"""The interaction session: one code path for record, replay, counterfactual and branch runs.

Every model call, tool call and nondeterministic read goes through :meth:`Session.interact`.
The session decides — based on its mode, the reference recording and the fault plan —
whether to execute the operation, serve it from the recording, or inject a fault, and it
records exactly one event describing what happened and where the response came from.
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..core.canonical import deep_diff, stable_hash, to_jsonable
from ..core.clock import Clock
from ..core.errors import (
    GhostReplayError,
    MissingRecordingError,
    ReplayDivergenceError,
    ToolError,
)
from ..models import (
    Divergence,
    ErrorInfo,
    Event,
    EventKind,
    EventSource,
    Execution,
    ExecutionMode,
    FaultSpec,
    ReplayAnnotation,
    ReplayVerdict,
)
from ..mutation import FaultPlan, apply_fault
from ..recorder import Recorder

_UNSET: Any = object()


@dataclass
class Operation:
    kind: EventKind
    name: str
    request: Any
    destructive: bool = False
    model: str | None = None
    timeout_ms: float | None = None
    observe: Callable[[], Any] | None = None
    match_request: Any = _UNSET
    parent_event_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


OFFLINE_MODES = frozenset({ExecutionMode.REPLAY, ExecutionMode.COUNTERFACTUAL_REPLAY})


class Session:
    """Policy engine for interactions.

    * ``record``: execute live (source ``live``); faults may still be injected.
    * ``replay`` / ``counterfactual-replay``: never execute anything. Serve the next recorded
      interaction if it matches; otherwise record a divergence and raise.
    * ``branch``: tools are re-executed against a fresh simulated environment and verified
      against the recording; model responses and nondeterminism come from the recording while
      the run is on-track; after the first divergence everything executes live, labelled
      ``simulated``.
    """

    def __init__(
        self,
        recorder: Recorder,
        *,
        mode: ExecutionMode,
        clock: Clock,
        reference: Execution | None = None,
        faults: list[FaultSpec] | None = None,
    ) -> None:
        if mode in OFFLINE_MODES and reference is None:
            raise ValueError(f"{mode} requires a reference recording")
        if mode == ExecutionMode.BRANCH and reference is None:
            raise ValueError("branch mode requires a reference recording")
        self.recorder = recorder
        self.mode = mode
        self.clock = clock
        self.reference = reference
        self.plan = FaultPlan(faults)
        if self.offline and self.plan.requires_branch:
            raise ValueError("these faults require branch execution, not offline replay")
        self._expected: list[Event] = reference.interactions() if reference else []
        self._cursor = 0
        self.on_track = reference is not None
        self._occurrences: Counter[tuple[str, str]] = Counter()
        self.faults_applied = 0
        self.divergence: Divergence | None = None

    @property
    def offline(self) -> bool:
        return self.mode in OFFLINE_MODES

    @property
    def consumed(self) -> int:
        return self._cursor

    # ------------------------------------------------------------------------------------
    def interact(self, op: Operation, invoke: Callable[[], Any]) -> tuple[Any, Event]:
        """Perform (or replay) one interaction. Returns ``(response, event)``.

        Raises the (recorded or injected) ``ToolError`` after recording it, and
        ``ReplayDivergenceError`` when an offline run diverges.
        """
        if self.offline and self.divergence is not None:
            raise ReplayDivergenceError(
                "replay already diverged; no further interactions can be served",
                divergence=self.divergence.model_dump(),
            )

        timestamp = self.clock.now().isoformat()
        t0 = self.clock.monotonic_ms()
        match_req = op.request if op.match_request is _UNSET else op.match_request
        redacted_req = self.recorder.redactor.redact(to_jsonable(match_req))
        key = stable_hash(op.kind.value, op.name, redacted_req)
        self._occurrences[(op.kind.value, op.name)] += 1
        occurrence = self._occurrences[(op.kind.value, op.name)]

        # 1. Divergence check against the reference --------------------------------------
        expected: Event | None = None
        annotation: ReplayAnnotation | None = None
        if self.reference is not None and self.on_track:
            candidate = self._expected[self._cursor] if self._cursor < len(self._expected) else None
            problem = self._check(op, key, redacted_req, candidate)
            if problem is None:
                expected = candidate
                self._cursor += 1
                annotation = ReplayAnnotation(
                    verdict=ReplayVerdict.MATCHED,
                    recorded_event_id=candidate.event_id if candidate else None,
                    recorded_seq=candidate.seq if candidate else None,
                )
            else:
                self._diverge(problem)
                if self.offline:
                    if problem.type == "unexpected_call":
                        raise MissingRecordingError(
                            problem.message, divergence=problem.model_dump()
                        )
                    raise ReplayDivergenceError(problem.message, divergence=problem.model_dump())
                annotation = ReplayAnnotation(
                    verdict=ReplayVerdict.DIVERGED, detail=problem.message
                )
        elif self.reference is not None:
            annotation = ReplayAnnotation(
                verdict=ReplayVerdict.LIVE, detail="executed after divergence"
            )

        # 2. Decide where the response comes from ------------------------------------------
        serve_recorded = expected is not None and (self.offline or op.kind != EventKind.TOOL_CALL)
        execute: Callable[[], Any] | None = None if self.offline else invoke

        def recorded() -> Any:
            assert expected is not None
            if expected.error is not None:
                raise ToolError.from_info(expected.error.model_dump())
            return copy.deepcopy(expected.response)

        state_before: Any = None
        if expected is not None and self.offline:
            state_before = copy.deepcopy(expected.state_before)
        elif op.observe is not None and not self.offline:
            state_before = op.observe()

        fault = self.plan.match(op.kind.value, op.name, op.request, occurrence)
        response: Any = None
        error: ToolError | None = None
        applied = None
        crash: BaseException | None = None
        if fault is not None:
            outcome = apply_fault(
                fault,
                op_name=op.name,
                clock=self.clock,
                timeout_ms=op.timeout_ms,
                baseline=recorded if serve_recorded else invoke,
                execute=execute,
                recorded_response=copy.deepcopy(expected.response) if expected else None,
                recorded_error=expected.error if expected else None,
            )
            response, error, applied = outcome.response, outcome.error, outcome.applied
            source = EventSource.INJECTED
            self.faults_applied += 1
            if annotation is not None and annotation.verdict == ReplayVerdict.MATCHED:
                annotation.verdict = ReplayVerdict.SUBSTITUTED
                annotation.detail = f"recorded response replaced by fault {fault.id}"
        else:
            try:
                if serve_recorded:
                    source = EventSource.RECORDED
                    response = recorded()
                else:
                    source = (
                        EventSource.LIVE
                        if self.mode == ExecutionMode.RECORD
                        else EventSource.SIMULATED
                    )
                    response = invoke()
            except ToolError as exc:
                error = exc
            except GhostReplayError:
                raise
            except Exception as exc:  # a bug in a tool handler or model adapter
                crash = exc
                error = ToolError(f"{type(exc).__name__}: {exc}")
                error.error_type = "InternalError"

        if serve_recorded and expected is not None and fault is None:
            self.clock.advance(expected.duration_ms)
        duration = self.clock.monotonic_ms() - t0

        state_after: Any = None
        if expected is not None and self.offline:
            state_after = copy.deepcopy(expected.state_after)
        elif op.observe is not None and not self.offline:
            state_after = op.observe()

        error_info = ErrorInfo(**error.to_info()) if error else None
        verify_problem: Divergence | None = None
        if (
            self.mode == ExecutionMode.BRANCH
            and expected is not None
            and fault is None
            and op.kind == EventKind.TOOL_CALL
        ):
            verify_problem = self._verify(expected, response, error_info)
            if verify_problem is not None and annotation is not None:
                annotation.verdict = ReplayVerdict.DIVERGED
                annotation.detail = verify_problem.message

        event = self.recorder.emit(
            op.kind,
            op.name,
            source=source,
            timestamp=timestamp,
            duration_ms=duration,
            parent_event_id=op.parent_event_id,
            model=op.model,
            request=op.request,
            response=response,
            error=error_info,
            state_before=state_before,
            state_after=state_after,
            match_key=key,
            destructive=op.destructive,
            fault=applied,
            replay=annotation,
            metadata=op.metadata,
        )
        if verify_problem is not None:
            verify_problem.at_seq = event.seq
            self._diverge(verify_problem)

        if crash is not None:
            raise crash
        if error is not None:
            error.event_id = event.event_id  # type: ignore[attr-defined]
            raise error
        return response, event

    # ------------------------------------------------------------------------------------
    def finish(self) -> None:
        """Report recorded interactions the agent never reached."""
        if self.reference is not None and self.on_track and self._cursor < len(self._expected):
            remaining = self._expected[self._cursor :]
            nxt = remaining[0]
            self._diverge(
                Divergence(
                    type="incomplete",
                    recorded_seq=nxt.seq,
                    expected=_describe(nxt),
                    message=(
                        f"Agent finished but {len(remaining)} recorded interaction(s) were never "
                        f"reached, starting with {nxt.kind.value} '{nxt.name}' (recorded seq {nxt.seq})"
                    ),
                    after_fault=self.faults_applied > 0,
                )
            )

    # ------------------------------------------------------------------------------------
    def _check(
        self, op: Operation, key: str, redacted_req: Any, expected: Event | None
    ) -> Divergence | None:
        actual = {"kind": op.kind.value, "name": op.name, "request": redacted_req}
        after_fault = self.faults_applied > 0
        if expected is None:
            return Divergence(
                type="unexpected_call",
                actual=actual,
                message=(
                    f"Missing recording: agent issued {op.kind.value} '{op.name}' but the "
                    f"recording has no interactions left ({len(self._expected)} recorded)"
                ),
                after_fault=after_fault,
            )
        if expected.kind != op.kind or expected.name != op.name:
            return Divergence(
                type="mismatch",
                recorded_seq=expected.seq,
                expected=_describe(expected),
                actual=actual,
                message=(
                    f"Execution path changed: recording expected {expected.kind.value} "
                    f"'{expected.name}' (seq {expected.seq}) but agent issued "
                    f"{op.kind.value} '{op.name}'"
                ),
                after_fault=after_fault,
            )
        if expected.match_key != key:
            changes = deep_diff(expected.request, redacted_req)[:25]
            paths = ", ".join(c["path"] for c in changes[:4]) or "request"
            return Divergence(
                type="mismatch",
                recorded_seq=expected.seq,
                expected=_describe(expected),
                actual=actual,
                changes=changes,
                message=(
                    f"Inputs changed for {op.kind.value} '{op.name}' (recorded seq "
                    f"{expected.seq}): {paths}"
                ),
                after_fault=after_fault,
            )
        return None

    def _verify(self, expected: Event, response: Any, error: ErrorInfo | None) -> Divergence | None:
        redact = self.recorder.redactor.redact
        actual_resp = redact(to_jsonable(response))
        actual_err = error.model_dump() if error else None
        expected_err = expected.error.model_dump() if expected.error else None
        if actual_resp == expected.response and _same_error(actual_err, expected_err):
            return None
        changes = deep_diff(
            {"response": expected.response, "error": expected_err},
            {"response": actual_resp, "error": redact(actual_err)},
        )[:25]
        return Divergence(
            type="result_mismatch",
            recorded_seq=expected.seq,
            expected=_describe(expected),
            changes=changes,
            message=(
                f"Simulated backend returned a different result for '{expected.name}' than the "
                f"recording (seq {expected.seq})"
            ),
            after_fault=self.faults_applied > 0,
        )

    def _diverge(self, problem: Divergence) -> None:
        self.on_track = False
        if problem.at_seq is None:
            problem.at_seq = self.recorder.next_seq
        if self.divergence is None:
            self.divergence = problem
        self.recorder.emit(
            EventKind.DIVERGENCE,
            problem.type,
            source=EventSource.FRAMEWORK,
            request={"expected": problem.expected, "actual": problem.actual},
            response={
                "message": problem.message,
                "changes": problem.changes,
                "after_fault": problem.after_fault,
            },
            metadata={"recorded_seq": problem.recorded_seq},
        )


def _describe(event: Event) -> dict[str, Any]:
    return {
        "kind": event.kind.value,
        "name": event.name,
        "seq": event.seq,
        "event_id": event.event_id,
        "request": event.request,
    }


def _same_error(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    if a is None or b is None:
        return a is b
    return a.get("type") == b.get("type") and a.get("message") == b.get("message")
