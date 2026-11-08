# Quickstart

GhostReplay is a flight recorder and crash-test lab for AI agents. You route your agent's calls to the outside world (tools and model calls) through it. It records them, replays them offline, injects failures into them and turns incidents into pytest regressions.

This page takes about five minutes. Every code block on it runs as shown (they are executed by `tests/test_sdk_docs.py`).

## 1. Install

```bash
pip install "ghostreplay @ git+https://github.com/thosuperman/ghost-replay@main#subdirectory=packages/ghostreplay"
```

Python 3.12+. The SDK depends only on `pydantic`. See [installation](installation.md) for other options.

## 2. Instrument and record

```python
from ghostreplay import GhostReplay

ghost = GhostReplay("my-agent")  # in memory; pass storage="./ghostreplay-data" to keep runs
ORDERS = {"ORD-123": {"id": "ORD-123", "total_cents": 12900}}


@ghost.tool("orders.lookup")
def lookup_order(order_id: str) -> dict:
    return ORDERS[order_id]  # your real code


@ghost.agent()
def handle(task: dict) -> dict:
    order = lookup_order(task["order_id"])
    return {"status": "success", "message": f"Found {order['id']}"}


run = ghost.record({"order_id": "ORD-123"})
print(run.explain())
```

`record` runs your agent for real. `lookup_order` executes, and the call, its arguments and its result are stored as an event.

## 3. Replay offline

```python
from ghostreplay import GhostReplay

ghost = GhostReplay("my-agent")
calls = []


@ghost.tool("orders.lookup")
def lookup_order(order_id: str) -> dict:
    calls.append(order_id)
    return {"id": order_id}


@ghost.agent()
def handle(task: dict) -> dict:
    return {"status": "success", "message": lookup_order(task["order_id"])["id"]}


run = ghost.record({"order_id": "ORD-123"})
again = ghost.replay(run)
assert calls == ["ORD-123"]  # only the recording executed the tool
assert again.live_calls == 0 and again.replayed_calls == 1
assert ghost.diff(run, again).identical
```

A replay re-runs your agent code, but every routed call is answered from the recording. Your tool function is not called, so nothing is charged, refunded or deleted twice.

## 4. Break it on purpose and prove the fix

[`examples/quickstart.py`](examples/quickstart.py) is the full workflow in about 90 lines:

- a model call;
- a payment tool;
- a buggy and a fixed agent;
- a safety invariant;
- a timeout-after-commit fault;
- an offline replay;
- regression tests for both agents.

```bash
cd docs/sdk/examples && python quickstart.py
```

```text
rec_… [record] agent=buggy status=completed
  output (success): charged
  [FAIL] charges.at_most_once: customer charged 2 times
replay: completed, live calls 0
buggy: FAIL (expected FAIL)
fixed: PASS (expected PASS)
```

## Next

- [Instrumentation](instrumentation.md): what gets recorded and what does not.
- [Failure injection](failure-injection.md) and [regression testing](regression-testing.md).
- [CI integration](ci-integration.md).
- A complete separate app: [`examples/invoice-agent`](../../examples/invoice-agent/README.md).
