"""GhostReplay quickstart: record, break, replay and regression-test your own agent.

pip install ./packages/ghostreplay        # from a checkout of the repository
python quickstart.py
"""

from ghostreplay import GhostReplay, ToolTimeout, TraceView, fault

ghost = GhostReplay("shop-agent", storage="./ghostreplay-data")
LEDGER: list[dict] = []  # a simulated payment service


@ghost.reset
def reset() -> None:  # runs before each recording: start from the same world
    LEDGER.clear()


@ghost.state
def state() -> dict:  # captured after each run, for invariants
    return {"charges": list(LEDGER)}


# 1. Instrument: only decorated calls are recorded and replayed.
@ghost.model("planner")
def plan(question: str) -> dict:
    return {"action": "charge", "amount_cents": 12900}  # call your LLM here


@ghost.tool("payments.charge", destructive=True)
def charge(order_id: str, amount_cents: int, key: str | None = None) -> dict:
    for c in LEDGER:
        if key and c["key"] == key:
            return c  # idempotent: same key, same charge
    LEDGER.append({"id": f"ch_{len(LEDGER) + 1}", "order_id": order_id, "key": key})
    return LEDGER[-1]


# 2. Your agent: plain Python that calls the decorated functions.
@ghost.agent("buggy")
def buggy(task: dict) -> dict:
    decision = plan(question=f"Customer asks about {task['order_id']}")
    for _ in range(2):
        try:
            charge(task["order_id"], decision["amount_cents"])
            return {"status": "success", "message": "charged"}
        except ToolTimeout:
            continue  # BUG: the first charge may already have succeeded
    return {"status": "failed", "message": "gave up"}


@ghost.agent("fixed", fix=True)
def fixed(task: dict) -> dict:
    decision = plan(question=f"Customer asks about {task['order_id']}")
    key = ghost.new_id("charge")  # recorded, so replays use the same key
    for _ in range(2):
        try:
            charge(task["order_id"], decision["amount_cents"], key)
            return {"status": "success", "message": "charged"}
        except ToolTimeout:
            continue  # safe: the key makes the retry idempotent
    return {"status": "failed", "message": "gave up"}


# 3. What "safe" means for this agent.
@ghost.invariant("charges.at_most_once", requires_state=True)
def at_most_once(view: TraceView) -> bool | str:
    n = len(view.final_state["charges"])
    return n <= 1 or f"customer charged {n} times"


# 4. Record a failure, replay it offline, fix it, and prove the fix.
timeout = [fault("timeout_after_commit", "payments.charge")]
incident = ghost.record({"order_id": "ORD-1"}, agent="buggy", faults=timeout)
print(incident.explain())  # FAIL charges.at_most_once: customer charged 2 times

replay = ghost.replay(incident)  # no model or tool function is called
print(f"replay: {replay.status}, live calls {replay.live_calls}")

for agent in ("buggy", "fixed"):
    report = ghost.check(ghost.regression_case(incident, agent=agent))
    print(f"{agent}: {report.verdict} (expected {report.expect.upper()})")

ghost.write_regression_test(incident, "tests/regression", agent="fixed", import_module="quickstart")
