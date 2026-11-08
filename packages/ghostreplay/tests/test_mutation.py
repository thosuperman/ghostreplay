"""Guarantees of the Counterfactual Failure Lab."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from ghostreplay.core.clock import VirtualClock
from ghostreplay.core.errors import RateLimited, ToolTimeout
from ghostreplay.models import EventSource, ExecutionMode, ExecutionStatus, FaultSpec, FaultTarget
from ghostreplay.mutation import CATALOG, apply_fault
from ghostreplay.server import create_app


def _fault(
    kind: str, name: str = "bank.withdraw", occurrence: int | None = 1, **params
) -> FaultSpec:
    return FaultSpec(
        id=f"t-{kind}",
        kind=kind,
        target=FaultTarget(name=name, occurrence=occurrence),
        params=params,
    )


def test_catalog_covers_required_faults():
    required = {
        "tool_timeout",
        "http_429",
        "http_500",
        "missing_field",
        "null_value",
        "duplicate_response",
        "delayed_operation",
        "stale_data",
        "incorrect_output",
        "auth_failure",
        "permission_denied",
        "partial_success",
        "timeout_after_commit",
        "reordered_response",
        "clock_skew",
    }
    assert required <= set(CATALOG)
    assert CATALOG["clock_skew"].strategy == "transform"
    assert not CATALOG["clock_skew"].requires_branch
    assert CATALOG["reordered_response"].strategy == "transform"
    assert not CATALOG["reordered_response"].requires_branch
    assert CATALOG["timeout_after_commit"].requires_branch
    assert not CATALOG["http_500"].requires_branch


def test_branch_fault_reproduces_double_withdrawal_and_fix_prevents_it(lab):
    base = lab.record("toy-bank", "naive")
    assert all(i.status == "passed" for i in base.invariants)
    fault = [_fault("timeout_after_commit")]
    naive = lab.counterfactual(base.id, fault)
    assert naive.mode == ExecutionMode.BRANCH  # chosen automatically: needs a real side effect
    injected = [e for e in naive.events if e.source == EventSource.INJECTED]
    assert len(injected) == 1 and injected[0].fault.operation_executed
    assert injected[0].error.type == "ToolTimeout"
    assert len(naive.final_state["bank"]["withdrawals"]) == 2
    assert {i.id: i.status for i in naive.invariants}["bank.no_double_withdrawal"] == "failed"

    safe = lab.counterfactual(base.id, fault, variant="safe")
    assert len(safe.final_state["bank"]["withdrawals"]) == 1
    assert {i.id: i.status for i in safe.invariants}["bank.no_double_withdrawal"] == "passed"


def test_offline_counterfactual_stops_instead_of_inventing_a_continuation(lab, counters):
    base = lab.record("toy-bank", "naive")
    counters.handler_calls = counters.model_calls = 0
    cf = lab.counterfactual(base.id, [_fault("http_500", name="bank.balance")], mode="replay")
    assert cf.mode == ExecutionMode.COUNTERFACTUAL_REPLAY
    assert counters.handler_calls == 0 and counters.model_calls == 0
    faulted = next(e for e in cf.events if e.fault)
    assert faulted.replay.verdict == "substituted"
    assert (
        faulted.fault.original_response
        == next(e for e in base.events if e.name == "bank.balance").response
    )
    assert cf.status == ExecutionStatus.DIVERGED
    assert cf.divergence.after_fault
    assert cf.final_state is None
    assert any("branch mode" in n for n in cf.notes)
    by_id = {i.id: i.status for i in cf.invariants}
    assert by_id["bank.no_double_withdrawal"] == "inconclusive"


def test_same_fault_in_branch_mode_executes_continuation(lab):
    base = lab.record("toy-bank", "naive")
    cf = lab.counterfactual(base.id, [_fault("http_500", name="bank.balance")], mode="branch")
    assert cf.status == ExecutionStatus.COMPLETED
    assert cf.output.status == "escalated"
    assert any(e.source == EventSource.SIMULATED for e in cf.events if e.is_interaction)
    assert cf.final_state["bank"]["withdrawals"] == []


def test_branch_without_faults_stays_on_track_and_verifies_tools(lab):
    base = lab.record("toy-bank", "naive")
    cf = lab.counterfactual(base.id, [], mode="branch")
    assert cf.divergence is None
    assert cf.final_state == base.final_state
    tools = [e for e in cf.events if e.kind.value == "tool_call"]
    assert all(e.source == EventSource.SIMULATED and e.replay.verdict == "matched" for e in tools)


def test_requires_branch_faults_are_rejected_offline(lab):
    base = lab.record("toy-bank", "naive")
    with pytest.raises(ValueError):
        lab.counterfactual(base.id, [_fault("timeout_after_commit")], mode="replay")


def test_occurrence_targets_only_that_call(lab):
    base = lab.record("toy-bank", "naive")
    cf = lab.counterfactual(
        base.id, [_fault("http_500", name="bank.balance", occurrence=2)], mode="replay"
    )
    assert not any(e.fault for e in cf.events)  # balance is only called once
    assert cf.status == ExecutionStatus.COMPLETED


# --------------------------------------------------------------------------------------
# Direct fault application
# --------------------------------------------------------------------------------------


def _apply(kind: str, response, **params):
    return apply_fault(
        _fault(kind, **params),
        op_name="op",
        clock=VirtualClock(),
        timeout_ms=1000,
        baseline=lambda: response,
        execute=lambda: response,
    )


def test_transform_faults():
    resp = {"items": [{"id": 1, "status": "ok"}, {"id": 2, "status": "ok"}], "total": 2}
    assert "total" not in _apply("missing_field", resp, path="total").response
    assert _apply("null_value", resp, path="items.0.status").response["items"][0]["status"] is None
    out = _apply("incorrect_output", resp, set={"items.*.status": "impaired"}).response
    assert [i["status"] for i in out["items"]] == ["impaired", "impaired"]
    assert len(_apply("duplicate_response", resp).response["items"]) == 4
    assert resp["items"][0]["status"] == "ok"  # baseline untouched (deep copies)
    missing = _apply("missing_field", resp, path="nope")
    assert missing.response == resp and "not present" in missing.applied.description


def test_reordered_response_reverses_or_rotates_without_touching_the_baseline():
    resp = {"meta": {"page": 1}, "items": [{"id": 1}, {"id": 2}, {"id": 3}]}
    reversed_ = _apply("reordered_response", resp)
    assert [i["id"] for i in reversed_.response["items"]] == [3, 2, 1]
    assert reversed_.applied.kind == "reordered_response" and reversed_.error is None
    rotated = _apply("reordered_response", resp, path="items", rotate=1).response
    assert [i["id"] for i in rotated["items"]] == [2, 3, 1]
    assert [i["id"] for i in _apply("reordered_response", resp, rotate=-1).response["items"]] == [
        3,
        1,
        2,
    ]
    assert [i["id"] for i in resp["items"]] == [1, 2, 3]  # baseline untouched
    assert _apply("reordered_response", [1, 2, 3]).response == [3, 2, 1]  # top-level list


def test_reordered_response_leaves_response_unchanged_when_path_is_missing_or_not_a_list():
    resp = {"items": [1, 2], "total": 2}
    missing = _apply("reordered_response", resp, path="nope")
    assert missing.response == resp and "not present" in missing.applied.description
    scalar = _apply("reordered_response", resp, path="total")
    assert scalar.response == resp and "not a list" in scalar.applied.description
    no_list = _apply("reordered_response", {"total": 2})
    assert no_list.response == {"total": 2} and "no list" in no_list.applied.description


def test_reordered_response_in_offline_counterfactual_is_injected(lab):
    base = lab.record("toy-bank", "naive")
    tool = next(e for e in base.events if e.kind.value == "tool_call")
    cf = lab.counterfactual(base.id, [_fault("reordered_response", name=tool.name)], mode="replay")
    assert cf.mode == ExecutionMode.COUNTERFACTUAL_REPLAY
    faulted = next(e for e in cf.events if e.fault)
    assert faulted.source == EventSource.INJECTED
    assert faulted.fault.kind == "reordered_response"


def test_faults_endpoint_lists_reordered_response(lab):
    client = TestClient(create_app(lab))
    kinds = {k["id"]: k for k in client.get("/api/faults").json()}
    assert kinds["reordered_response"]["strategy"] == "transform"
    assert set(kinds["reordered_response"]["params"]) == {"path", "rotate"}


def test_clock_skew_shifts_iso_timestamps_and_keeps_their_format():
    assert (
        _apply("clock_skew", "2026-01-01T00:00:00+00:00", skew_ms=3_600_000).response
        == "2026-01-01T01:00:00+00:00"
    )
    assert _apply("clock_skew", "2026-01-01T00:00:00Z", skew_ms=-1_500).response == (
        "2025-12-31T23:59:58.500000Z"
    )
    assert _apply("clock_skew", "2026-01-01T00:00:00", skew_ms=1000).response == (
        "2026-01-01T00:00:01"
    )


def test_clock_skew_leaves_non_timestamps_unchanged_with_a_note():
    bad = _apply("clock_skew", "not a time", skew_ms=1000)
    assert bad.response == "not a time" and "not an ISO timestamp" in bad.applied.description
    obj = _apply("clock_skew", {"t": 1}, skew_ms=1000)
    assert obj.response == {"t": 1} and "not an ISO timestamp" in obj.applied.description
    no_skew = _apply("clock_skew", "2026-01-01T00:00:00Z")
    assert no_skew.response == "2026-01-01T00:00:00Z" and "skew_ms" in no_skew.applied.description


def test_clock_skew_on_clock_now_is_injected_and_offline_replay_still_matches(lab, counters):
    base = lab.record("toy-bank", "naive")
    recorded = next(e for e in base.events if e.name == "clock.now")
    counters.handler_calls = counters.model_calls = 0
    skew = FaultSpec(
        id="t-clock_skew",
        kind="clock_skew",
        target=FaultTarget(kind="nondeterminism", name="clock.now"),
        params={"skew_ms": -86_400_000},
    )
    cf = lab.counterfactual(base.id, [skew], mode="auto")
    assert cf.mode == ExecutionMode.COUNTERFACTUAL_REPLAY  # replay-safe: stays offline
    assert counters.handler_calls == 0 and counters.model_calls == 0
    faulted = next(e for e in cf.events if e.fault)
    assert faulted.kind.value == "nondeterminism" and faulted.name == "clock.now"
    assert faulted.source == EventSource.INJECTED
    assert faulted.replay.verdict == "substituted"
    assert faulted.fault.original_response == recorded.response
    shift = datetime.fromisoformat(recorded.response) - datetime.fromisoformat(faulted.response)
    assert shift == timedelta(days=1)
    # The toy agent ignores the time, so the rest of the recording is served unchanged.
    assert cf.status == ExecutionStatus.COMPLETED and cf.divergence is None
    others = [e for e in cf.events if e.is_interaction and e is not faulted]
    assert others and all(e.replay.verdict == "matched" for e in others)


def test_error_and_delay_faults():
    assert isinstance(_apply("http_429", {}).error, RateLimited)
    assert _apply("permission_denied", {}).error.error_type == "PermissionDenied"
    slow = _apply("delayed_operation", {"ok": 1}, delay_ms=5000)
    assert isinstance(slow.error, ToolTimeout) and slow.applied.operation_executed
    fast = _apply("delayed_operation", {"ok": 1}, delay_ms=10)
    assert fast.error is None and fast.response == {"ok": 1}


def test_unknown_fault_kind_rejected():
    with pytest.raises(ValueError):
        _apply("meteor_strike", {})
