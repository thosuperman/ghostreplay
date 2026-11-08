# Replay

`ghost.replay(run)` re-runs your current agent code against a recording:

- Every model call, tool call, id and timestamp your code asks for is answered from the recording, in order.
- No decorated function is called. During a replay, tool handlers are replaced by stubs that raise `OfflineViolation` if they are ever reached.
- The outcome is recomputed by your code, and the invariants are evaluated again.

```python
from ghostreplay import GhostReplay, ToolTimeout, fault

ghost = GhostReplay("payer")
PAID: list[int] = []


@ghost.reset
def reset() -> None:
    PAID.clear()


@ghost.tool("bank.pay", destructive=True)
def pay(amount: int) -> dict:
    PAID.append(amount)
    return {"ok": True}


@ghost.agent()
def agent(task: dict) -> dict:
    for _ in range(2):
        try:
            pay(task["amount"])
            return {"status": "success", "message": "paid"}
        except ToolTimeout:
            continue
    return {"status": "failed", "message": "gave up"}


incident = ghost.record({"amount": 100}, faults=[fault("timeout_after_commit", "bank.pay")])
assert PAID == [100, 100]  # the bug: paid twice

PAID.clear()
replay = ghost.replay(incident)
assert PAID == []  # nothing was paid during the replay
assert replay.status == "completed" and replay.live_calls == 0
print(replay.explain())
```

## Divergence

If your code now asks for something different, GhostReplay stops at that call. For example it might pass different arguments, call another tool, or make an extra call. The run then reports:

- `status="diverged"`;
- a `divergence` describing the expected vs actual call, with field-level changes.

It never guesses a response and never executes the tool to fill the gap.

```python
from ghostreplay import GhostReplay

ghost = GhostReplay("lookup")


@ghost.tool("orders.get")
def get(order_id: str) -> dict:
    return {"id": order_id}


@ghost.agent("v1")
def v1(task: dict) -> str:
    return get("A")["id"]


@ghost.agent("v2")
def v2(task: dict) -> str:  # the code changed: it now asks for a different order
    return get("B")["id"]


run = ghost.record({}, agent="v1")
# A replay always uses the recorded agent; simulate a code change by re-registering it.
ghost.agent("v1")(v2)
diverged = ghost.replay(run)
print(diverged.status, "-", diverged.execution.divergence.message)
```

This is what makes a replay a test: "identical" means your current code makes the same decisions on the same inputs.

## Replay vs re-execution

| | Strict replay (`replay`) | Mutated re-execution (`inject(..., mode="branch")`, or `record` with faults) |
|---|---|---|
| Your tool functions | Never called | Called (against your simulated services) after the divergence point |
| Model functions | Never called | Called after the divergence point |
| Use it to | Reproduce an incident, check a refactor changes nothing | See what *new* code or a *new* failure would do |
| Labelled | `mode="replay"`, events `source="recorded"` | `mode="branch"`, events after the fork `source="live"` |

To test a fix, run the fixed agent, either with `record(task, agent="fixed", faults=...)` or with `inject(run, faults, agent="fixed")`. Replaying the old recording with changed code is meant to diverge.

## From the command line

```bash
ghostreplay replay traces/rec_123.trace.json --app my_agent.agent:ghost
```

This loads the trace into the app's store and replays it with your code. It exits with 0 when the replay completes identically, and 1 otherwise.
