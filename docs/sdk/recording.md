# Recording

`ghost.record(task, agent=..., faults=..., title=...)` runs your agent for real and stores a run, which is a versioned trace (an `Execution`) containing:

- **The input:** `task`.
- **Every routed interaction, in order:** model calls, tool calls, ids, time and agent steps. Each carries arguments, result or error, timing, and `source="live"`.
- **The state:** an initial and a final snapshot from `@ghost.state`.
- **The outcome:** the agent's output, and the verdict of every invariant.
- **Provenance:** which model produced the decisions (scripted or live).

```python
from ghostreplay import GhostReplay, TraceView

ghost = GhostReplay("greeter", default_task={"name": "Ada"})
SENT: list[str] = []


@ghost.reset
def reset() -> None:
    SENT.clear()


@ghost.state
def state() -> dict:
    return {"sent": list(SENT)}


@ghost.tool("mail.send", destructive=True)
def send(to: str, body: str) -> dict:
    SENT.append(to)
    return {"queued": True}


@ghost.agent()
def agent(task: dict) -> dict:
    send(to=task["name"], body=f"Hello {task['name']} ({ghost.new_id('msg')})")
    return {"status": "success", "message": "sent"}


@ghost.invariant("mail.once", "At most one email per run", requires_state=True)
def once(view: TraceView) -> bool:
    return len(view.final_state["sent"]) <= 1


run = ghost.record()  # uses default_task
print(run.explain())
print(
    [
        (e.seq, e.kind.value, e.name, e.source.value)
        for e in run.events
        if e.kind.value != "agent_step"
    ]
)
```

## Storage

- `GhostReplay(app, storage="./ghostreplay-data")` keeps runs in `./ghostreplay-data/<app>.sqlite3` (SQLite in WAL mode).
- `storage=None` (the default) keeps them in memory for the lifetime of the object, which suits tests.
- `ghost.runs()` lists stored run ids, and `ghost.get(id)` loads one.
- `ghost.export(run, "traces/")` writes a portable JSON file (see [trace import/export](trace-import-export.md)).

## Redaction

Before an event is stored, GhostReplay redacts values under sensitive keys (`api_key`, `token`, `password`, `authorization`, `secret`, `cookie` and similar) and values that look like credentials (`sk-…`, bearer tokens, AWS access keys, GitHub tokens). Replay matching uses the same redaction, so secrets never need to be in a trace for a replay to work.

## Reset and state

The `@ghost.reset` hook runs before each run so every recording starts from the same simulated world. `@ghost.state` is captured after each executed run. Invariants that need it declare `requires_state=True`. During an offline counterfactual there is no fresh final state, so those invariants report `inconclusive` instead of guessing.

## Faults while recording

`record(..., faults=[fault("timeout_after_commit", "payments.charge")])` injects the failure into the live run. The faulted event is labelled `source="injected"` and carries a `fault` record of what was changed. See [failure injection](failure-injection.md).
