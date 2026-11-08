"""The developer-facing SDK: instrument your own Python agent with a few decorators.

GhostReplay only records what is routed through it. With this module that means:

* functions decorated with :meth:`GhostReplay.tool` (calls to the outside world),
* functions decorated with :meth:`GhostReplay.model` (calls to an LLM or any other model),
* :meth:`GhostReplay.complete` when you use a ``ModelAdapter`` such as the Anthropic adapter,
* :meth:`GhostReplay.step` annotations.

Anything else your code does (direct HTTP requests, database queries, reading the clock) is
invisible to GhostReplay and will not be replayed. There is no automatic instrumentation.

Example::

    ghost = GhostReplay("invoice-agent", storage="./ghostreplay-data")

    @ghost.tool("payments.pay", destructive=True)
    def pay(invoice_id: str, amount_cents: int) -> dict: ...

    @ghost.agent("buggy")
    def run(task: dict) -> dict:
        receipt = pay(task["invoice_id"], 12900)
        return {"status": "success", "message": f"paid {receipt['id']}"}

    run1 = ghost.record({"invoice_id": "INV-1"}, agent="buggy")
    again = ghost.replay(run1)       # offline: no tool or model function is called
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import functools
import inspect
import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar

from .core.clock import Clock
from .core.errors import GhostReplayError
from .diff import TraceDiff, diff_executions
from .lab.lab import Lab
from .lab.registry import register
from .lab.scenario import Environment, Scenario, Variant
from .mocking.model import ModelAdapter, ModelRequest, ModelResponse
from .mocking.tools import ToolRegistry, ToolSpec
from .models import (
    AgentResult,
    Event,
    EventKind,
    Execution,
    ExecutionStatus,
    FaultSpec,
    FaultTarget,
    InvariantResult,
)
from .mutation import CATALOG
from .regression.cases import RegressionCase, RegressionReport
from .regression.generate import write_case
from .regression.invariants import Check, Invariant, TraceView
from .replay.session import Operation
from .runtime import AgentRuntime
from .storage import SqliteStore, export_execution
from .storage.parsing import parse_document

F = TypeVar("F", bound=Callable[..., Any])

_current: contextvars.ContextVar[_ActiveRun | None] = contextvars.ContextVar(
    "ghostreplay_active_run", default=None
)
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,79}$")


@dataclass
class _ActiveRun:
    ghost: GhostReplay
    rt: AgentRuntime


def fault(
    kind: str,
    tool: str,
    *,
    occurrence: int | None = 1,
    where: dict[str, Any] | None = None,
    target: Literal["tool_call", "model_call"] = "tool_call",
    id: str | None = None,
    **params: Any,
) -> FaultSpec:
    """Build a :class:`FaultSpec`, e.g. ``fault("timeout_after_commit", "payments.pay")``.

    ``kind`` is one of the 13 kinds in ``ghostreplay.mutation.CATALOG``; ``occurrence`` is
    1-based (``None`` = every call); extra keyword arguments become the fault's ``params``.
    """
    if kind not in CATALOG:
        raise ValueError(f"unknown fault kind {kind!r}; known: {', '.join(CATALOG)}")
    return FaultSpec(
        id=id or f"{kind}.{tool}.{occurrence or 'all'}"[:80],
        kind=kind,
        target=FaultTarget(kind=target, name=tool, occurrence=occurrence, where=where or {}),
        params=params,
    )


class Run:
    """One stored execution, with helpers for the questions you usually ask about it."""

    def __init__(self, execution: Execution) -> None:
        self.execution = execution

    # -- identity / outcome ------------------------------------------------------------
    @property
    def id(self) -> str:
        return self.execution.id

    @property
    def mode(self) -> str:
        return self.execution.mode.value

    @property
    def agent(self) -> str:
        return self.execution.variant

    @property
    def status(self) -> str:
        """``completed``, ``diverged`` (replay no longer matches the recording) or ``failed``."""
        return self.execution.status.value

    @property
    def output(self) -> AgentResult | None:
        return self.execution.output

    @property
    def invariants(self) -> list[InvariantResult]:
        return self.execution.invariants

    @property
    def failed_invariants(self) -> list[str]:
        return [i.id for i in self.execution.invariants if i.status == "failed"]

    @property
    def passed(self) -> bool:
        """True when the run completed and no invariant failed."""
        return self.execution.status == ExecutionStatus.COMPLETED and not self.failed_invariants

    @property
    def diverged(self) -> bool:
        return self.execution.divergence is not None

    @property
    def final_state(self) -> dict[str, Any] | None:
        return self.execution.final_state

    # -- events ---------------------------------------------------------------------------
    @property
    def events(self) -> list[Event]:
        return self.execution.events

    def tool_calls(self, name: str | None = None) -> list[Event]:
        return [
            e
            for e in self.execution.events
            if e.kind == EventKind.TOOL_CALL and (name is None or e.name == name)
        ]

    def model_calls(self) -> list[Event]:
        return [e for e in self.execution.events if e.kind == EventKind.MODEL_CALL]

    @property
    def live_calls(self) -> int:
        """Model and tool calls that were really executed (0 for a strict replay)."""
        return sum(
            1
            for e in self.execution.events
            if e.kind in (EventKind.TOOL_CALL, EventKind.MODEL_CALL) and e.source.value == "live"
        )

    @property
    def replayed_calls(self) -> int:
        """Model and tool calls served from the recording."""
        return sum(
            1
            for e in self.execution.events
            if e.kind in (EventKind.TOOL_CALL, EventKind.MODEL_CALL)
            and e.source.value == "recorded"
        )

    def explain(self) -> str:
        ex = self.execution
        lines = [f"{ex.id} [{ex.mode.value}] agent={ex.variant} status={ex.status.value}"]
        if ex.output is not None:
            lines.append(f"  output ({ex.output.status}): {ex.output.message}")
        if ex.divergence is not None:
            lines.append(f"  divergence: {ex.divergence.message}")
        for inv in ex.invariants:
            mark = {"passed": "PASS", "failed": "FAIL", "inconclusive": "????"}[inv.status]
            lines.append(f"  [{mark}] {inv.id}: {inv.message}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<Run {self.id} {self.mode} {self.status} failed={self.failed_invariants}>"


class _SdkModel:
    """Provenance stand-in when the app makes its model calls through ``@ghost.model``."""

    provider = "app-defined"

    def __init__(self, ghost: GhostReplay) -> None:
        self.model = f"{ghost.app}-model"
        self.is_live = ghost.live_models
        names = ", ".join(sorted(ghost._models)) or "none registered"
        kind = "live model call(s)" if ghost.live_models else "deterministic model function(s)"
        self.label = f"App-defined {kind} recorded through @ghost.model wrappers ({names})"

    def complete(self, request: ModelRequest) -> ModelResponse:  # pragma: no cover - guard
        raise GhostReplayError(
            "this GhostReplay app has no ModelAdapter; pass model=... to GhostReplay(...) to use "
            "ghost.complete(), or wrap your model function with @ghost.model"
        )


class _FunctionAgent:
    def __init__(self, name: str, fn: Callable[[dict[str, Any]], Any], ghost: GhostReplay):
        self.name = name
        self._fn = fn
        self._ghost = ghost

    def run(self, rt: AgentRuntime, task: dict[str, Any]) -> AgentResult:
        token = _current.set(_ActiveRun(self._ghost, rt))
        try:
            if inspect.iscoroutinefunction(self._fn):
                result = _run_coroutine(self._fn(task))
            else:
                result = self._fn(task)
        finally:
            _current.reset(token)
        return _as_result(result)


def _as_result(value: Any) -> AgentResult:
    if isinstance(value, AgentResult):
        return value
    if isinstance(value, dict):
        status = value.get("status", "success")
        message = str(value.get("message", ""))
        data = {k: v for k, v in value.items() if k not in ("status", "message")}
        return AgentResult(status=status, message=message, data=data)
    if value is None:
        return AgentResult(status="success", message="")
    return AgentResult(status="success", message=str(value))


def _run_coroutine(coro: Any) -> Any:
    """Run a coroutine to completion from synchronous engine code.

    The engine is synchronous; async tools and agents run on a private event loop in a worker
    thread (with the caller's context), so this also works when called from inside a loop.
    """
    ctx = contextvars.copy_context()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(ctx.run, asyncio.run, coro).result()


class _SdkScenario(Scenario):
    """Adapts a :class:`GhostReplay` app to the engine's ``Scenario`` interface."""

    def __init__(self, ghost: GhostReplay) -> None:
        self.ghost = ghost
        self.id = ghost.app
        self.app = ghost.app
        self.title = ghost.title
        self.summary = ghost.description
        self.bug_explanation = ""
        self.fix_explanation = ""
        self.conditions = ()
        self.headline_invariant = ""

    @property
    def variants(self) -> tuple[Variant, ...]:  # type: ignore[override]
        return tuple(
            Variant(name, name, spec["description"], is_fix=spec["fix"])
            for name, spec in self.ghost._agents.items()
        )

    def default_task(self) -> dict[str, Any]:
        return dict(self.ghost.default_task)

    def build_environment(self, conditions: dict[str, str], clock: Clock) -> Environment:
        if self.ghost._reset is not None:
            self.ghost._reset()
        tools = ToolRegistry()
        for spec in self.ghost._tools.values():
            tools.register(spec)
        snapshot = self.ghost._state or dict
        return Environment(tools=tools, snapshot=lambda: snapshot(), clock=clock)

    def build_model(self) -> ModelAdapter:
        return self.ghost.model_adapter or _SdkModel(self.ghost)

    def build_agent(self, variant: str) -> _FunctionAgent:
        spec = self.ghost._agents[variant]
        return _FunctionAgent(f"{self.ghost.app}/{variant}", spec["fn"], self.ghost)

    def invariants(self) -> list[Invariant]:
        return list(self.ghost._invariants)


class GhostReplay:
    """Record, replay, break and regression-test your own agent.

    Args:
        app: Name of your application (also the scenario id in regression cases).
        storage: Directory for the SQLite store; ``None`` or ``":memory:"`` keeps everything
            in memory.
        model: Optional ``ModelAdapter`` (scripted or a live provider adapter) for
            :meth:`complete`. Not needed when you wrap model functions with :meth:`model`.
        live_models: Set ``True`` when your ``@ghost.model`` functions call a real LLM, so
            recordings are labelled as live model output.
        default_task: Input used when :meth:`record` is called without a task.
    """

    def __init__(
        self,
        app: str,
        *,
        storage: str | Path | None = None,
        model: ModelAdapter | None = None,
        live_models: bool = False,
        default_task: dict[str, Any] | None = None,
        title: str | None = None,
        description: str = "",
    ) -> None:
        if not _NAME.match(app):
            raise ValueError(f"invalid app name {app!r} (letters, digits, . _ -)")
        self.app = app
        self.title = title or app
        self.description = description
        self.model_adapter = model
        self.live_models = live_models
        self.default_task = dict(default_task or {})
        self._tools: dict[str, ToolSpec] = {}
        self._models: set[str] = set()
        self._agents: dict[str, dict[str, Any]] = {}
        self._invariants: list[Invariant] = []
        self._state: Callable[[], dict[str, Any]] | None = None
        self._reset: Callable[[], Any] | None = None
        if storage is None or str(storage) == ":memory:":
            store = SqliteStore(":memory:")
        else:
            store = SqliteStore(Path(storage) / f"{app}.sqlite3")
        self.store = store
        self.scenario = _SdkScenario(self)
        register(self.scenario)  # lets generated regression tests find this app by name
        self._lab = Lab(app, [self.scenario], store)

    # ------------------------------------------------------------------------------------
    # Instrumentation
    # ------------------------------------------------------------------------------------
    def tool(
        self,
        name: str | None = None,
        *,
        description: str = "",
        destructive: bool = False,
        observe: Callable[[dict[str, Any]], Any] | None = None,
        match_fields: list[str] | None = None,
    ) -> Callable[[F], F]:
        """Route calls to the decorated function through GhostReplay.

        Inside :meth:`record` the call is executed and recorded; inside :meth:`replay` the
        recorded result (or error) is returned and the function is **not** called. Outside a
        GhostReplay run the function behaves exactly as before. Arguments and return values
        must be JSON-serialisable. Raise ``ghostreplay.ToolError`` subclasses (``ToolTimeout``,
        ``RateLimited``, ``HttpError`` …) for failures you want recorded and replayed.
        ``observe(args)`` may return the slice of state the call changes; it is captured
        before and after the call. Works with ``def`` and ``async def`` functions.
        """

        def deco(fn: F) -> F:
            tool_name = name or fn.__name__
            if not _NAME.match(tool_name):
                raise ValueError(f"invalid tool name {tool_name!r}")
            if tool_name in self._tools:
                raise ValueError(f"tool {tool_name!r} registered twice")
            sig = inspect.signature(fn)
            is_async = inspect.iscoroutinefunction(fn)

            def handler(**kwargs: Any) -> Any:
                if is_async:
                    return _run_coroutine(fn(**kwargs))
                return fn(**kwargs)

            self._tools[tool_name] = ToolSpec(
                name=tool_name,
                handler=handler,
                description=description or (fn.__doc__ or "").strip().split("\n")[0],
                category="agent",
                destructive=destructive,
                observe=observe,
                match_fields=match_fields,
            )

            def call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
                active = _current.get()
                bound = sig.bind(*args, **kwargs)
                return active.rt.call_tool(tool_name, dict(bound.arguments))  # type: ignore[union-attr]

            if is_async:

                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    if _current.get() is None:
                        return await fn(*args, **kwargs)
                    return call(args, kwargs)

                return async_wrapper  # type: ignore[return-value]

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                if _current.get() is None:
                    return fn(*args, **kwargs)
                return call(args, kwargs)

            return wrapper  # type: ignore[return-value]

        return deco

    def model(self, name: str) -> Callable[[F], F]:
        """Record calls to a model function (an LLM client call, a classifier, …).

        The decorated function takes JSON-serialisable keyword arguments (e.g. ``prompt=``)
        and returns a JSON-serialisable result. During replay the recorded result is returned
        and the function is not called, so no API request is made.
        """
        if not _NAME.match(name):
            raise ValueError(f"invalid model name {name!r}")

        def deco(fn: F) -> F:
            self._models.add(name)
            sig = inspect.signature(fn)
            is_async = inspect.iscoroutinefunction(fn)

            def call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
                active = _current.get()
                assert active is not None
                request = dict(sig.bind(*args, **kwargs).arguments)

                def invoke() -> Any:
                    if is_async:
                        return _run_coroutine(fn(**request))
                    return fn(**request)

                response, _ = active.rt.session.interact(
                    Operation(kind=EventKind.MODEL_CALL, name=name, model=name, request=request),
                    invoke,
                )
                return response

            if is_async:

                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    if _current.get() is None:
                        return await fn(*args, **kwargs)
                    return call(args, kwargs)

                return async_wrapper  # type: ignore[return-value]

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                if _current.get() is None:
                    return fn(*args, **kwargs)
                return call(args, kwargs)

            return wrapper  # type: ignore[return-value]

        return deco

    def agent(
        self, name: str = "default", *, fix: bool = False, description: str = ""
    ) -> Callable[[F], F]:
        """Register an agent entry point ``fn(task: dict) -> dict | str | AgentResult``.

        Register several (e.g. ``"buggy"`` and ``"fixed"`` with ``fix=True``) to compare them
        under the same faults. A returned dict may carry ``status`` (success, failed,
        escalated, partial, refused) and ``message``; other keys become result data.
        """
        if not _NAME.match(name):
            raise ValueError(f"invalid agent name {name!r}")

        def deco(fn: F) -> F:
            self._agents[name] = {"fn": fn, "fix": fix, "description": description or name}
            return fn

        return deco

    def invariant(
        self,
        id: str,
        title: str | None = None,
        *,
        severity: Literal["critical", "high", "medium", "low"] = "high",
        description: str = "",
        requires_state: bool = False,
    ) -> Callable[[F], F]:
        """Register a safety check ``fn(view: TraceView) -> bool | str | Check``.

        Return ``True`` (or a ``Check.ok``) when the run is safe. Return ``False``, a failure
        message string or ``Check.fail(...)`` when it is not. ``view`` gives the recorded
        events, tool calls, final state and output.
        """

        def deco(fn: F) -> F:
            def check(view: TraceView) -> Check:
                result = fn(view)
                if isinstance(result, Check):
                    return result
                if result is True or result is None:
                    return Check.ok(title or id)
                if result is False:
                    return Check.fail(f"{title or id}: violated")
                return Check.fail(str(result))

            self._invariants.append(
                Invariant(
                    id=id,
                    title=title or id,
                    description=description or title or id,
                    check=check,
                    severity=severity,
                    requires_state=requires_state,
                )
            )
            return fn

        return deco

    def add_invariant(self, invariant: Invariant) -> Invariant:
        """Add a ready-made invariant, e.g. ``ghostreplay.invariants.max_successful_calls``."""
        self._invariants.append(invariant)
        return invariant

    def state(self, fn: F) -> F:
        """Register ``fn() -> dict`` returning the simulated state to capture after each run."""
        self._state = fn
        return fn

    def reset(self, fn: F) -> F:
        """Register ``fn()`` called before every run to reset your simulated services, so
        each recording starts from the same world. (It also runs before replays, where no
        tool is called, so keep it side-effect free apart from resetting that state.)"""
        self._reset = fn
        return fn

    # -- calls made from inside an agent ------------------------------------------------
    def step(self, name: str, **detail: Any) -> None:
        """Record an agent-declared step (e.g. ``ghost.step("retry", attempt=2)``)."""
        active = _current.get()
        if active is not None:
            active.rt.log(name, detail)

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Call the configured ``ModelAdapter`` through GhostReplay (recorded / replayed)."""
        active = _current.get()
        if active is None:
            if self.model_adapter is None:
                raise GhostReplayError("no model adapter configured")
            return self.model_adapter.complete(request)
        return active.rt.complete(request).response

    def new_id(self, prefix: str = "id") -> str:
        """A recorded id (replayed identically). Use it for idempotency keys and the like."""
        active = _current.get()
        if active is None:
            import uuid

            return f"{prefix}_{uuid.uuid4().hex[:12]}"
        return active.rt.new_id(prefix)

    def now(self) -> str:
        """Current time as ISO 8601, recorded during a run and replayed identically."""
        active = _current.get()
        if active is None:
            from datetime import UTC, datetime

            return datetime.now(UTC).isoformat()
        return active.rt.now()

    @property
    def model_name(self) -> str:
        """Model id to put in ``ModelRequest.model`` (works during replay too)."""
        active = _current.get()
        if active is not None:
            return active.rt.model_name
        if self.model_adapter is None:
            raise GhostReplayError("no model adapter configured")
        return self.model_adapter.model

    # ------------------------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------------------------
    def _agent_name(self, agent: str | None) -> str:
        if not self._agents:
            raise GhostReplayError("register an agent first with @ghost.agent(...)")
        if agent is None:
            if len(self._agents) == 1:
                return next(iter(self._agents))
            if "default" in self._agents:
                return "default"
            raise GhostReplayError(
                f"several agents registered; pass agent= one of {list(self._agents)}"
            )
        if agent not in self._agents:
            raise GhostReplayError(f"unknown agent {agent!r}; registered: {list(self._agents)}")
        return agent

    @staticmethod
    def _id(run: Run | Execution | str) -> str:
        if isinstance(run, Run):
            return run.id
        if isinstance(run, Execution):
            return run.id
        return run

    def record(
        self,
        task: dict[str, Any] | None = None,
        *,
        agent: str | None = None,
        faults: Iterable[FaultSpec] = (),
        title: str = "",
    ) -> Run:
        """Execute the agent for real (your tool and model functions are called) and record
        every routed interaction. ``faults`` are injected into matching calls and labelled."""
        name = self._agent_name(agent)
        ex = self._lab.record(
            self.scenario.id,
            name,
            faults=list(faults),
            title=title or f"{name} run",
            task=task if task is not None else self.default_task,
        )
        return Run(ex)

    async def arecord(self, task: dict[str, Any] | None = None, **kwargs: Any) -> Run:
        """``record`` for async callers (runs the engine in a worker thread)."""
        return await asyncio.to_thread(self.record, task, **kwargs)

    def replay(self, run: Run | Execution | str) -> Run:
        """Strict offline replay: re-run the same agent code, serving every model and tool
        response from the recording. No decorated function is called. If the agent asks for
        something the recording does not contain, the replay stops with ``status="diverged"``.
        """
        return Run(self._lab.replay(self._id(run)))

    def inject(
        self,
        run: Run | Execution | str,
        faults: Iterable[FaultSpec],
        *,
        agent: str | None = None,
        mode: Literal["auto", "replay", "branch"] = "auto",
        title: str = "",
    ) -> Run:
        """Counterfactual: replay ``run`` with faults injected.

        ``mode="replay"`` stays fully offline and stops at the first divergence. ``"branch"``
        replays up to the fault, then re-executes the rest against your (simulated) tools,
        optionally with a different ``agent``. ``"auto"`` picks branch when needed.
        """
        ex = self._lab.counterfactual(
            self._id(run),
            list(faults),
            variant=self._agent_name(agent) if agent else None,
            mode=mode,
            title=title,
        )
        return Run(ex)

    def get(self, run_id: str) -> Run:
        return Run(self.store.get(run_id))

    def runs(self, limit: int = 50) -> list[str]:
        return [s.id for s in self.store.list(app=self.app, limit=limit)]

    def diff(self, a: Run | Execution | str, b: Run | Execution | str) -> TraceDiff:
        """Structural diff of two runs, including the first point where they diverge."""
        ea = (
            a.execution
            if isinstance(a, Run)
            else a
            if isinstance(a, Execution)
            else self.store.get(a)
        )
        eb = (
            b.execution
            if isinstance(b, Run)
            else b
            if isinstance(b, Execution)
            else self.store.get(b)
        )
        return diff_executions(ea, eb)

    # ------------------------------------------------------------------------------------
    # Traces and regression tests
    # ------------------------------------------------------------------------------------
    def export(self, run: Run | Execution | str, directory: str | Path) -> Path:
        """Write ``<id>.trace.json`` (versioned, already-redacted JSON) into ``directory``."""
        ex = (
            run.execution
            if isinstance(run, Run)
            else run
            if isinstance(run, Execution)
            else self.store.get(run)
        )
        return export_execution(ex, directory)

    def load(self, path: str | Path) -> Run:
        """Validate a trace file and add it to this app's store (data only, never executed)."""
        p = Path(path)
        ex = parse_document(Execution, p.read_bytes(), source=f"trace file {p.name}")
        if ex.app != self.app:
            raise GhostReplayError(f"trace belongs to app {ex.app!r}, not {self.app!r}")
        self.store.save(ex)
        return Run(ex)

    def regression_case(
        self,
        run: Run | Execution | str,
        *,
        agent: str | None = None,
        expect: Literal["pass", "fail"] | None = None,
        case_id: str | None = None,
    ) -> RegressionCase:
        """Turn a run into a regression case (re-run ``agent`` under the same input/faults).

        ``expect`` defaults to ``"pass"`` for agents registered with ``fix=True``."""
        return self._lab.case_from_execution(
            self._id(run),
            variant=self._agent_name(agent) if agent else None,
            expect=expect,
            case_id=case_id,
        )

    def check(self, case: RegressionCase) -> RegressionReport:
        """Run a regression case now and report whether its invariants hold."""
        return self._lab.run_case(case)

    def write_regression_test(
        self,
        run: Run | Execution | str,
        directory: str | Path,
        *,
        agent: str | None = None,
        expect: Literal["pass", "fail"] | None = None,
        case_id: str | None = None,
        import_module: str | None = None,
    ) -> tuple[Path, Path]:
        """Write ``<case>.case.json`` and a pytest module that re-runs it.

        ``import_module`` is the module that creates this ``GhostReplay`` app (for example
        ``"invoice_agent.agent"``); the generated test imports it so the app is registered.
        """
        case = self.regression_case(run, agent=agent, expect=expect, case_id=case_id)
        return write_case(case, directory, import_module=import_module)

    def __iter__(self) -> Iterator[str]:  # pragma: no cover - convenience
        return iter(self.runs())


__all__ = ["GhostReplay", "Run", "fault"]
