# Limitations

These are limits of the current SDK. Please read them before relying on GhostReplay for something important.

## Instrumentation is explicit

- Only calls routed through `@ghost.tool`, `@ghost.model`, `ghost.complete`, `ghost.new_id` and `ghost.now` are recorded and replayed.
- There's no automatic patching of HTTP clients, databases, LLM SDKs or the clock.
- Code that reads hidden state can behave differently on replay without GhostReplay noticing. Hidden state means globals, environment variables, `datetime.now()`, `random`, or files read outside a tool. GhostReplay only detects a difference once it changes a routed call.

## Values must be JSON

Tool and model arguments and results must be JSON-serialisable. Binary payloads, file handles and SDK objects must be converted at the boundary.

## Replay needs your code

- A trace is data. Replaying it requires the agent code that produced it, with matching tool and model names, passed explicitly (`ghostreplay replay TRACE --app module:ghost`).
- A recording made with old code is expected to diverge from new code that behaves differently. To test new code under an old incident, re-execute it with `record(..., agent=..., faults=...)` or `inject(..., mode="branch")`.

## Sequential runs

- The engine runs one agent at a time per `GhostReplay` object, and records calls in the order your agent makes them.
- Concurrent calls from several threads or `asyncio.gather` inside one run are not supported: replay matches calls by order. Make the calls sequentially inside a run.
- Async agents and tools run on a private event loop in a worker thread.

## Simulated services are yours

GhostReplay doesn't simulate your backends. Branch-mode re-execution and `record` call your real tool functions. Point them at fakes, sandboxes or in-memory services (as the examples do) whenever a re-execution must not touch production.

## Fault coverage

The 13 fault kinds model common API and data failures. Some failures can't be expressed as a fault on a single call and are not modelled: process crashes, partial network partitions, clock skew, and concurrent writers. Faults that need the real operation (`timeout_after_commit`, `delayed_operation`, `partial_success`) can't be applied in a purely offline replay.

## Distribution and versions

- The package is not on PyPI yet. Install it from GitHub or from a checkout.
- The trace schema is `ghostreplay/v1`. Traces from another schema version are rejected rather than migrated.
- Python 3.12+.

## The hosted demo

<https://ghostreplay.hayaix.tech> runs only the two bundled labs:

- It never executes visitor code.
- Uploaded traces are inspection-only unless they come from those labs.
- Visitor data expires after 24 hours.

## Common errors

| Message | Cause | Fix |
|---|---|---|
| `register an agent first with @ghost.agent(...)` | `record` was called before any agent was registered | Decorate your entry point |
| `several agents registered; pass agent=…` | More than one agent and no `"default"` | Pass `agent="name"` |
| `Missing recording … (unexpected_call)` in a divergence | Your code made a call the recording doesn't contain | Expected after a code change; re-record or re-execute |
| `Inputs changed for tool_call 'X'` | Same call, different arguments | Check for hidden state (time, ids, random); use `ghost.new_id()` / `ghost.now()` |
| `scenario 'my-agent' is not registered` (CLI / pytest) | The module that creates your `GhostReplay` wasn't imported | Use `--import my_agent.agent` / `import_module=` |
| `trace belongs to app 'x', not 'y'` | Loading another app's trace | Load it into the matching `GhostReplay` |
| `TypeError: Value of type … is not JSON-serialisable` (run `status="failed"`) | A tool or model function returned a non-JSON value | Convert at the boundary |
