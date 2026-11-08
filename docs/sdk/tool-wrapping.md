# Tool wrapping

A tool is any function your agent uses to read from or act on the world: an HTTP API, a database, a payment gateway or a cloud SDK. Decorate it with `@ghost.tool`.

```python
from ghostreplay import GhostReplay, RateLimited

ghost = GhostReplay("inventory-agent")
STOCK = {"SKU-1": 3}


@ghost.tool("inventory.get", description="Units in stock for a SKU")
def get_stock(sku: str) -> dict:
    return {"sku": sku, "units": STOCK.get(sku, 0)}


@ghost.tool(
    "inventory.reserve",
    destructive=True,  # marks it in timelines, diffs and invariants
    observe=lambda args: {"units": STOCK.get(args["sku"], 0)},  # captured before and after
)
def reserve(sku: str, units: int) -> dict:
    if units > STOCK.get(sku, 0):
        raise RateLimited("inventory API: too many requests")  # a replayable failure
    STOCK[sku] -= units
    return {"sku": sku, "reserved": units}


@ghost.agent()
def agent(task: dict) -> dict:
    if get_stock(task["sku"])["units"] >= task["units"]:
        return {"status": "success", "message": str(reserve(task["sku"], task["units"]))}
    return {"status": "refused", "message": "not enough stock"}


run = ghost.record({"sku": "SKU-1", "units": 2})
call = run.tool_calls("inventory.reserve")[0]
print(call.state_before, "->", call.state_after)  # {'units': 3} -> {'units': 1}
```

## Options

| Option | Meaning |
|---|---|
| `name` | Event name (defaults to the function name). Faults and invariants target tools by name. |
| `description` | Shown in schemas and the dashboard (defaults to the first docstring line) |
| `destructive=True` | Marks calls that change the world (payments, deletions). It's highlighted everywhere and counted in diffs. |
| `observe(args) -> state` | Called before and after the real call; the results become `state_before` / `state_after`. This makes side effects visible even when the call itself fails, which is how GhostReplay shows that a timed-out payment really committed. |
| `match_fields=[...]` | Match replays only on these arguments (default: all arguments). Use it when an argument such as a free-text reason may legitimately vary. |

## How calls are matched during replay

Each recorded interaction has a match key built from its kind, its name and a hash of its redacted arguments. During replay the agent's calls must arrive in the same order with the same key. If one doesn't match, the replay stops with `status="diverged"`, and `run.execution.divergence` says what changed (for example `Inputs changed for tool_call 'payments.charge': idempotency_key`). GhostReplay never serves a different recording "close enough", and never falls back to executing the tool.

## Sync, async and outside a run

- `def` and `async def` tools both work. An async tool is awaited as usual by your code.
- Outside `record`, `replay` and `inject`, a decorated function behaves exactly like the original, so your tests and production code can call it directly.
