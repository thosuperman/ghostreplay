# Python API

Everything below is importable from `ghostreplay`. The engine underneath (`ghostreplay.lab`, `ghostreplay.replay`) is also public, but you don't need it to use the SDK.

```python
# fragment
from ghostreplay import GhostReplay, Run, fault, TraceView, Check, ToolTimeout
from ghostreplay.invariants import errors_surfaced, max_successful_calls
```

## `GhostReplay(app, *, storage=None, model=None, live_models=False, default_task=None, title=None, description="")`

One instrumented application.

| Argument | Meaning |
|---|---|
| `app` | Your application's name: letters, digits, `.`, `_` or `-`. It is also the scenario id in regression cases. |
| `storage` | Directory for the SQLite run store (`<storage>/<app>.sqlite3`). `None` or `":memory:"` keeps runs in memory. |
| `model` | An optional `ModelAdapter` (for example `ScriptedModel`, or the Anthropic adapter) used by `ghost.complete()` |
| `live_models` | Set `True` when your `@ghost.model` functions call a real LLM, so recordings are labelled as live model output |
| `default_task` | Input used by `record()` when no task is given |

Creating a `GhostReplay` registers it by `app` name, so regression cases and generated tests can find it after its module is imported.

### Instrumentation decorators

| Decorator | Use it on | Effect |
|---|---|---|
| `@ghost.tool(name=None, *, description="", destructive=False, observe=None, match_fields=None)` | Functions that reach the outside world (`def` or `async def`) | Routed through the runtime during a run: executed and recorded, served from the recording in replay, faults injected. Outside a run it behaves like the plain function. |
| `@ghost.model(name)` | A function that calls a model (`def` or `async def`), taking JSON-able keyword arguments | Recorded as a model call. Served from the recording in replay, so no API request is made. |
| `@ghost.agent(name="default", *, fix=False, description="")` | Your agent entry point `fn(task: dict)` | Returns a `dict`, `str` or `AgentResult`. Register several (for example `"buggy"` and a `fix=True` `"fixed"`) to compare them. |
| `@ghost.invariant(id, title=None, *, severity="high", description="", requires_state=False)` | `fn(view: TraceView) -> bool \| str \| Check` | A safety rule evaluated after every run. `True` means it passed. `False`, a message or `Check.fail(...)` means it failed. |
| `@ghost.state` | `fn() -> dict` | Simulated state captured after each executed run (`run.final_state`) |
| `@ghost.reset` | `fn()` | Called before every run to reset your simulated services |

Calls you make from inside an agent:

| Call | Records |
|---|---|
| `ghost.step(name, **detail)` | An agent annotation, such as `ghost.step("retry", attempt=2)`. `recovers=<event_id>` marks recovery from a failed call. |
| `ghost.new_id(prefix="id")` | A unique id that replays identically. Use it for idempotency keys. |
| `ghost.now()` | The current time as ISO 8601, replayed identically |
| `ghost.complete(ModelRequest)` | A call to the configured `ModelAdapter` |
| `ghost.model_name` | The model id to put in `ModelRequest.model` (also works during replay) |

### Running

| Method | Returns | What it does |
|---|---|---|
| `record(task=None, *, agent=None, faults=(), title="")` | `Run` | Executes the agent for real and records it. `faults` are injected into matching calls. |
| `await arecord(...)` | `Run` | `record` for async callers |
| `replay(run)` | `Run` | Strict offline replay of `run`. No decorated function is called. `status="diverged"` if the code asks for something the recording does not contain. |
| `inject(run, faults, *, agent=None, mode="auto")` | `Run` | Counterfactual run. `"replay"` stays offline and stops at the first divergence. `"branch"` replays up to the fault and then re-executes, optionally with another agent. |
| `diff(a, b)` | `TraceDiff` | Structural diff: aligned events, changed arguments, behaviour, invariants, first divergence |
| `get(run_id)` / `runs(limit=50)` | `Run` / `list[str]` | Read the store |

`run` arguments accept a `Run`, an `Execution` or a run id.

### Traces and regressions

| Method | Returns | What it does |
|---|---|---|
| `export(run, directory)` | `Path` | Writes `<id>.trace.json` (versioned and redacted) |
| `load(path)` | `Run` | Validates a trace file of this app and adds it to the store (data only) |
| `regression_case(run, *, agent=None, expect=None, case_id=None)` | `RegressionCase` | Re-runs `agent` with the same input and faults. `expect` defaults to `"pass"` for `fix=True` agents and `"fail"` otherwise. |
| `check(case)` | `RegressionReport` | Runs a case now. `report.verdict` is `"PASS"` or `"FAIL"`; check `report.outcome_matches_expectation`. |
| `write_regression_test(run, directory, *, agent=None, expect=None, case_id=None, import_module=None)` | `(case_path, test_path)` | Writes `<case>.case.json` and a pytest module. `import_module` is your module that creates the `GhostReplay` object. |

## `Run`

| Attribute | Meaning |
|---|---|
| `id`, `mode` (`record` / `replay` / `counterfactual-replay` / `branch`), `agent`, `status` (`completed` / `diverged` / `failed`) | Identity and outcome |
| `output` | The agent's `AgentResult` (`status`, `message`, `data`) |
| `invariants`, `failed_invariants`, `passed` | Safety results. `passed` means the run completed and no invariant failed. |
| `diverged` | The replay no longer matches the recording |
| `final_state` | What `@ghost.state` returned after the run |
| `events`, `tool_calls(name=None)`, `model_calls()` | Recorded events (`Event` objects) |
| `live_calls`, `replayed_calls` | Model and tool calls executed vs served from the recording |
| `explain()` | A readable multi-line summary |
| `execution` | The underlying `Execution` model (the trace document) |

## `fault(kind, tool, *, occurrence=1, where=None, target="tool_call", id=None, **params)`

Builds a `FaultSpec`, for example `fault("timeout_after_commit", "payments.charge")`. See [failure injection](failure-injection.md) for the 15 kinds. `target` is `"tool_call"`, `"model_call"` or `"nondeterminism"` (for `clock_skew` on `clock.now`).

## Invariants

`TraceView` (the `view` your invariant receives) provides:

- `events`;
- `tool_calls(name=None, succeeded=None)`;
- `model_calls()`;
- `steps(name=None)`;
- `guards()`;
- `final_state`;
- `output`;
- `before(event)` and `after(event)`.

`Check.ok(msg)`, `Check.fail(msg, evidence=(), explanation="")` and `Check.unknown(msg)` build explicit results.

Ready-made invariants in `ghostreplay.invariants`:

- `errors_surfaced(recovery_steps=("recovered",))`: tool errors must be recovered or reflected in the final status;
- `max_successful_calls(tool, limit, per=None)`.

Add them with `ghost.add_invariant(...)`.

## Errors to raise from tools

`ToolTimeout`, `RateLimited`, `HttpError`, `AuthError`, `PermissionDenied` and `PartialFailure` (all subclasses of `ToolError`) are recorded and re-raised identically during replay. Any other exception escaping your agent fails the run (`status="failed"`) and is recorded as an error.
