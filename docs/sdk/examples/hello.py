from ghostreplay import GhostReplay

ghost = GhostReplay("my-agent", storage="./ghostreplay-data")
ORDERS = {"ORD-123": {"id": "ORD-123", "total_cents": 12900}}  # stands in for your order API


@ghost.tool("orders.lookup")
def lookup_order(order_id: str) -> dict:
    return ORDERS[order_id]  # your real code runs here when recording


@ghost.agent()
def handle(task: dict) -> dict:
    order = lookup_order(task["order_id"])  # routed through GhostReplay
    return {"status": "success", "message": f"Found {order['id']}"}


run = ghost.record({"order_id": "ORD-123"})  # executes and records
again = ghost.replay(run)  # offline: lookup_order is NOT called
print(again.status, again.live_calls, ghost.diff(run, again).identical)  # completed 0 True
