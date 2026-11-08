# Failure injection

Production agents fail in ways that are hard to reproduce on demand. A timeout can hit after a payment already committed, a rate limit can arrive mid-retry, or monitoring can return stale data. GhostReplay injects these failures into a specific call, on purpose and with a label.

```python
# fragment
from ghostreplay import fault

fault("timeout_after_commit", "payments.charge")  # 1st call to payments.charge
fault("http_429", "orders.get", occurrence=None)  # every call
fault("stale_data", "monitor.health", set={"status": "impaired"})  # replace response fields
fault("tool_timeout", "kb.search", where={"q": "refunds"})  # only calls with these args
fault("incorrect_output", "planner", target="model_call", set={"action": "delete"})
```

## The 13 fault kinds

| Kind | Simulates | Needs re-execution* |
|---|---|---|
| `tool_timeout` | A timeout before the operation ran | |
| `timeout_after_commit` | The operation succeeded, but the caller sees a timeout | ✓ |
| `http_429` | Rate limited (`retry_after_s`) | |
| `http_500` | Server error | |
| `auth_failure` | Authentication failure | |
| `permission_denied` | Permission denied | |
| `missing_field` | A response field is missing (`path`) | |
| `null_value` | A response field is null (`path`) | |
| `duplicate_response` | List items duplicated (`path`) | |
| `stale_data` | Response fields replaced with stale values (`set`) | |
| `incorrect_output` | Response fields replaced with wrong values (`set`) | |
| `delayed_operation` | Added latency (`delay_ms`) | ✓ |
| `partial_success` | Operation partly applied, then an error (`message`) | ✓ |

\* These kinds need the real operation to run, so they cannot be applied in a purely offline replay. Use them in `record(...)` or `inject(..., mode="branch")`.

## Three ways to inject

```python
from ghostreplay import GhostReplay, ToolTimeout, TraceView, fault

ghost = GhostReplay("biller")
CHARGES: list[str] = []


@ghost.reset
def reset() -> None:
    CHARGES.clear()


@ghost.state
def state() -> dict:
    return {"charges": list(CHARGES)}


@ghost.tool("billing.charge", destructive=True)
def charge(customer: str, key: str | None = None) -> dict:
    if key and key in CHARGES:
        return {"duplicate_of": key}
    CHARGES.append(key or customer)
    return {"ok": True}


@ghost.agent("buggy")
def buggy(task: dict) -> dict:
    for _ in range(2):
        try:
            charge(task["customer"])
            return {"status": "success", "message": "charged"}
        except ToolTimeout:
            continue
    return {"status": "failed", "message": "gave up"}


@ghost.agent("fixed", fix=True)
def fixed(task: dict) -> dict:
    key = ghost.new_id("chg")
    for _ in range(2):
        try:
            charge(task["customer"], key)
            return {"status": "success", "message": "charged"}
        except ToolTimeout:
            continue
    return {"status": "failed", "message": "gave up"}


@ghost.invariant("billing.once", requires_state=True)
def once(view: TraceView) -> bool:
    return len(view.final_state["charges"]) <= 1


timeout = [fault("timeout_after_commit", "billing.charge")]
task = {"customer": "C-1"}

# 1. Record with the fault: a live run with the failure injected.
incident = ghost.record(task, agent="buggy", faults=timeout)

# 2. Counterfactual from a clean recording, offline: stops at the first behaviour change.
clean = ghost.record(task, agent="buggy")
offline = ghost.inject(clean, [fault("tool_timeout", "billing.charge")], mode="replay")

# 3. Counterfactual with re-execution, optionally with another agent ("mutated re-execution").
branch = ghost.inject(clean, timeout, agent="fixed", mode="branch")

print(incident.failed_invariants, offline.status, branch.passed)
```

Expected output: `['billing.once'] diverged True`. The buggy agent charged twice. The offline counterfactual stopped where the agent's behaviour changed after the fault. The fixed agent, re-executed under the same failure, passes.

## What gets labelled

- The faulted event has `source="injected"` and a `fault` record with its kind, strategy, whether the operation really executed, and the original response.
- Counterfactual runs keep a `reference_execution_id` pointing at the recording they came from.
- The dashboard and `ghostreplay inspect` show both.
