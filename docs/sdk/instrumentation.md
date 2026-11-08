# Instrumentation

GhostReplay records exactly what you route through it, and nothing else. This is deliberate: explicit instrumentation is what makes a replay trustworthy.

## What is recorded

| You write | Recorded as | During replay |
|---|---|---|
| A call to a `@ghost.tool` function | `tool_call` event: name, arguments, result or error, timing, optional state before/after | The recorded result or error is returned; the function is not called |
| A call to a `@ghost.model` function | `model_call` event: keyword arguments, result | The recorded result is returned; no API request |
| `ghost.complete(request)` | `model_call` event for a `ModelAdapter` | The recorded `ModelResponse` is returned |
| `ghost.new_id()`, `ghost.now()` | `nondeterminism` events | The same id / timestamp is returned |
| `ghost.step(name, ...)` | `agent_step` annotation | Re-emitted (annotations are compared but never "served") |
| Your agent's return value | the run's `output` | Recomputed by your code; compared by `diff` |

## What is NOT recorded

- Direct calls that bypass the decorators, such as `requests.get(...)`, an SDK client called inline, a database cursor or `open()`.
- Reads of global or module state, the system clock (`datetime.now()`), `random` and `uuid`.
- Anything inside a function you didn't decorate. Decorating your agent with `@ghost.agent` does not reach inside it.

If your agent does any of these, a replay may behave differently from the recording. When the difference reaches a routed call, GhostReplay reports it as a divergence. If it never reaches one, GhostReplay can't see it.

## The pattern

Wrap each boundary your agent crosses in one small decorated function, and call that from your agent:

```python
from ghostreplay import GhostReplay, ToolTimeout

ghost = GhostReplay("weather-agent")
FORECASTS = {"Tokyo": {"temp_c": 18}}  # stands in for an HTTP API


@ghost.tool("weather.get")
def get_weather(city: str) -> dict:
    if city not in FORECASTS:
        raise ToolTimeout(f"weather API timed out for {city}")
    return FORECASTS[city]  # e.g. httpx.get(f"https://api…/{city}").json()


@ghost.model("summarise")
def summarise(temp_c: int) -> str:
    return f"It's {temp_c}°C."  # e.g. an LLM call


@ghost.agent()
def agent(task: dict) -> dict:
    try:
        weather = get_weather(task["city"])
    except ToolTimeout:
        return {"status": "failed", "message": "weather service unavailable"}
    return {"status": "success", "message": summarise(temp_c=weather["temp_c"])}


ok = ghost.record({"city": "Tokyo"})
down = ghost.record({"city": "Atlantis"})
print(ok.output.message, "|", down.output.status)
assert ghost.replay(down).output.status == "failed"  # the recorded timeout is replayed
```

## Rules for instrumented functions

- **Arguments and results must be JSON-serialisable:** dicts, lists, strings, numbers, booleans, `None`. Convert dataclasses and SDK objects at the boundary.
- **Raise GhostReplay errors for failures you want replayed.** Use `ToolTimeout`, `RateLimited`, `HttpError`, `AuthError`, `PermissionDenied` or `PartialFailure`. Map your client's exceptions to these inside the decorated function.
- **Keep randomness and time behind the runtime.** Use `ghost.new_id()` and `ghost.now()` inside a run, or pass values in through the task.
- **Arguments are recorded as passed.** Default parameter values are not filled in, so pass the same arguments in your fixed code if you want a replay to match.
- **Names** must be 1–80 characters of letters, digits, `.`, `_` or `-`. Dotted names (`payments.charge`) read well in timelines.

## Async code

`async def` tools, model functions and agents are supported. The engine itself is synchronous: an async agent runs on a private event loop in a worker thread, and so does an async tool when it executes. From async application code, use `await ghost.arecord(...)`.

```python
import asyncio

from ghostreplay import GhostReplay

ghost = GhostReplay("async-agent")


@ghost.tool("db.fetch")
async def fetch(key: str) -> dict:
    await asyncio.sleep(0)
    return {"key": key, "value": 42}


@ghost.agent()
async def agent(task: dict) -> str:
    row = await fetch(task["key"])
    return f"value={row['value']}"


async def main() -> None:
    run = await ghost.arecord({"key": "a"})
    print(run.output.message, ghost.replay(run).live_calls)


asyncio.run(main())
```
