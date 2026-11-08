"""The public SDK (`ghostreplay.GhostReplay`): instrumentation, replay, faults, regressions."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys

import pytest

from ghostreplay import Check, GhostReplay, Run, ToolTimeout, TraceView, fault
from ghostreplay.cli import main as cli_main
from ghostreplay.invariants import max_successful_calls


def make_app(name: str = "sdk-test", *, storage=None) -> tuple[GhostReplay, dict]:
    """A tiny shop agent with a simulated order service. ``calls`` counts real executions."""
    calls = {"lookup": 0, "charge": 0, "model": 0}
    ledger: list[dict] = []
    ghost = GhostReplay(name, storage=storage, default_task={"order_id": "ORD-1"})

    @ghost.reset
    def _reset() -> None:
        ledger.clear()

    @ghost.state
    def _state() -> dict:
        return {"charges": list(ledger)}

    @ghost.model("planner")
    def plan(question: str) -> dict:
        calls["model"] += 1
        return {"action": "charge", "amount_cents": 500}

    @ghost.tool("orders.lookup")
    def lookup(order_id: str) -> dict:
        calls["lookup"] += 1
        return {"order_id": order_id, "total_cents": 500}

    @ghost.tool("payments.charge", destructive=True)
    async def charge(order_id: str, amount_cents: int, key: str | None = None) -> dict:
        calls["charge"] += 1
        for c in ledger:
            if key and c["key"] == key:
                return c
        receipt = {"id": f"ch_{len(ledger) + 1}", "order_id": order_id, "key": key}
        ledger.append(receipt)
        return receipt

    @ghost.agent("buggy")
    def buggy(task: dict) -> dict:
        order = lookup(task["order_id"])
        decision = plan(question=f"what to do with {order['order_id']}")
        for attempt in (1, 2):
            try:
                receipt = asyncio.run(charge(order["order_id"], decision["amount_cents"]))
                return {"status": "success", "message": f"charged {receipt['id']}"}
            except ToolTimeout:
                ghost.step("retry", attempt=attempt)
        return {"status": "failed", "message": "gave up"}

    @ghost.agent("fixed", fix=True)
    async def fixed(task: dict) -> dict:
        order = lookup(task["order_id"])
        decision = plan(question=f"what to do with {order['order_id']}")
        key = ghost.new_id("idem")
        for _ in (1, 2):
            try:
                receipt = await charge(order["order_id"], decision["amount_cents"], key)
                return {"status": "success", "message": f"charged {receipt['id']}"}
            except ToolTimeout:
                continue
        return {"status": "failed", "message": "gave up"}

    @ghost.invariant("charges.once", "An order is charged at most once", requires_state=True)
    def once(view: TraceView) -> bool | str:
        n = len((view.final_state or {}).get("charges", []))
        return True if n <= 1 else f"charged {n} times"

    ghost.add_invariant(max_successful_calls("orders.lookup", 1))
    return ghost, calls


TIMEOUT = [fault("timeout_after_commit", "payments.charge")]


def test_decorated_functions_behave_normally_outside_a_run():
    ghost, calls = make_app("sdk-plain")
    assert ghost.agent  # registered without error
    from ghostreplay.sdk import _current

    assert _current.get() is None
    run = ghost.record(agent="buggy")
    assert run.passed and calls == {"lookup": 1, "charge": 1, "model": 1}


def test_record_captures_tools_models_and_steps():
    ghost, _ = make_app("sdk-record")
    run = ghost.record(agent="buggy", faults=TIMEOUT)
    assert isinstance(run, Run) and run.mode == "record"
    assert [e.name for e in run.tool_calls()] == [
        "orders.lookup",
        "payments.charge",
        "payments.charge",
    ]
    assert [e.name for e in run.model_calls()] == ["planner"]
    assert run.tool_calls("payments.charge")[0].error.type == "ToolTimeout"
    assert run.failed_invariants == ["charges.once"]
    assert run.execution.provenance.model_is_live is False
    assert "@ghost.model" in run.execution.provenance.label


def test_strict_replay_calls_no_tool_or_model_function():
    ghost, calls = make_app("sdk-replay")
    incident = ghost.record(agent="buggy", faults=TIMEOUT)
    before = dict(calls)
    replay = ghost.replay(incident)
    assert calls == before, "replay executed a decorated function"
    assert replay.status == "completed"
    assert replay.live_calls == 0 and replay.replayed_calls == 4
    assert ghost.diff(incident, replay).identical
    assert replay.failed_invariants == ["charges.once"]


def test_replay_detects_changed_agent_behaviour():
    ghost, calls = make_app("sdk-diverge")
    rec = ghost.record(agent="buggy")
    lookup = ghost._tools["orders.lookup"]
    before = dict(calls)

    # The code changed since the recording: the agent now asks for a different order.
    @ghost.agent("buggy")
    def changed(task: dict) -> dict:
        from ghostreplay.sdk import _current

        _current.get().rt.call_tool(lookup.name, {"order_id": "ORD-999"})
        return {"status": "success", "message": "done"}

    rp = ghost.replay(rec)
    assert rp.status == "diverged" and rp.diverged
    assert "orders.lookup" in rp.execution.divergence.message
    assert calls == before, "a diverged replay must not fall back to executing the tool"


def test_fixed_async_agent_passes_under_the_same_fault_and_branch_switches_agent():
    ghost, _ = make_app("sdk-fixed")
    fixed = ghost.record(agent="fixed", faults=TIMEOUT)
    assert fixed.passed, fixed.explain()
    clean = ghost.record(agent="buggy")
    branch = ghost.inject(clean, TIMEOUT, agent="fixed")
    assert branch.mode == "branch" and branch.passed


def test_new_id_is_replayed_identically():
    ghost, _ = make_app("sdk-ids")
    run = ghost.record(agent="fixed", faults=TIMEOUT)
    assert ghost.diff(run, ghost.replay(run)).identical


def test_invariant_return_values():
    ghost = GhostReplay("sdk-inv")

    @ghost.agent()
    def agent(task: dict) -> str:
        return "ok"

    @ghost.invariant("a")
    def a(view: TraceView) -> bool:
        return True

    @ghost.invariant("b")
    def b(view: TraceView) -> bool:
        return False

    @ghost.invariant("c")
    def c(view: TraceView) -> str:
        return "custom failure"

    @ghost.invariant("d")
    def d(view: TraceView) -> Check:
        return Check.fail("explicit")

    run = ghost.record()
    status = {i.id: (i.status, i.message) for i in run.invariants}
    assert status["a"][0] == "passed"
    assert status["b"][0] == "failed"
    assert status["c"] == ("failed", "custom failure")
    assert status["d"] == ("failed", "explicit")
    assert run.output.message == "ok"


def test_regression_cases_and_generated_pytest(tmp_path):
    ghost, _ = make_app("sdk-regress")
    incident = ghost.record(agent="buggy", faults=TIMEOUT, task={"order_id": "ORD-7"})
    buggy = ghost.check(ghost.regression_case(incident, agent="buggy"))
    fixed = ghost.check(ghost.regression_case(incident, agent="fixed"))
    assert (buggy.verdict, buggy.expect) == ("FAIL", "fail")
    assert (fixed.verdict, fixed.expect) == ("PASS", "pass")
    case = ghost.regression_case(incident, agent="fixed")
    assert case.task == {"order_id": "ORD-7"}  # the custom input travels with the case

    _case, test = ghost.write_regression_test(
        incident, tmp_path, agent="buggy", import_module="x.y"
    )
    src = test.read_text()
    assert "import x.y  # noqa: F401" in src
    with pytest.raises(ValueError):
        ghost.write_regression_test(incident, tmp_path, import_module="os; import sys")


def test_export_load_and_cli(tmp_path, capsys):
    ghost, _ = make_app("sdk-cli", storage=tmp_path / "store")
    a = ghost.record(agent="buggy", faults=TIMEOUT)
    b = ghost.record(agent="fixed", faults=TIMEOUT)
    pa, pb = ghost.export(a, tmp_path), ghost.export(b, tmp_path)
    assert json.loads(pa.read_text())["schema_version"] == "ghostreplay/v1"

    assert cli_main(["inspect", str(pa), "--json"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["tool_errors"] == 1 and info["invariants"]["charges.once"] == "failed"

    assert cli_main(["diff", str(pa), str(pb)]) == 0
    assert "first divergence" in capsys.readouterr().out
    assert cli_main(["diff", str(pa), str(pb), "--fail-on-diff"]) == 1

    other = GhostReplay("other-app")
    with pytest.raises(Exception, match="belongs to app"):
        other.load(pa)

    assert (
        cli_main(
            [
                "export",
                a.id,
                "--store",
                str(tmp_path / "store"),
                "--app",
                "sdk-cli",
                "--out",
                str(tmp_path / "out"),
            ]
        )
        == 0
    )
    assert (tmp_path / "out" / f"{a.id}.trace.json").is_file()


def test_cli_rejects_malformed_traces(tmp_path):
    bad = tmp_path / "bad.trace.json"
    bad.write_text('{"not": "a trace"}')
    with pytest.raises(SystemExit, match=r"error: trace file bad\.trace\.json"):
        cli_main(["inspect", str(bad)])


def test_sdk_import_does_not_need_the_server_extra():
    code = "import sys, ghostreplay; ghostreplay.GhostReplay('x'); print('fastapi' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_invalid_names_are_rejected():
    with pytest.raises(ValueError):
        GhostReplay("../etc")
    ghost = GhostReplay("names")
    with pytest.raises(ValueError):
        ghost.tool("bad name with spaces")(lambda: None)
    with pytest.raises(ValueError):
        fault("not_a_kind", "x")
