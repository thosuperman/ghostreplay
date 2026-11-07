"""Guarantees of recording and deterministic offline replay."""

from __future__ import annotations

import socket
import threading

import pytest

from ghostreplay.core.clock import VirtualClock
from ghostreplay.core.errors import MissingRecordingError, OfflineViolation, ReplayDivergenceError
from ghostreplay.diff import diff_executions
from ghostreplay.models import (
    EventKind,
    EventSource,
    Execution,
    ExecutionMode,
    ExecutionStatus,
    Provenance,
    ReplayVerdict,
)
from ghostreplay.recorder import Recorder
from ghostreplay.replay import Operation, Session, offline_guard


def _comparable(ex: Execution) -> list[tuple]:
    return [
        (
            e.kind,
            e.name,
            e.request,
            e.response,
            e.error.model_dump() if e.error else None,
            e.timestamp,
            e.duration_ms,
            e.state_before,
            e.state_after,
            e.destructive,
            e.match_key,
        )
        for e in ex.events
        if e.kind
        in (
            EventKind.MODEL_CALL,
            EventKind.TOOL_CALL,
            EventKind.NONDETERMINISM,
            EventKind.AGENT_STEP,
        )
    ]


def test_recording_has_ordered_complete_events(lab):
    ex = lab.record("toy-bank", "naive")
    assert ex.status == ExecutionStatus.COMPLETED
    assert [e.seq for e in ex.events] == list(range(len(ex.events)))
    kinds = [e.kind for e in ex.events]
    assert kinds[0] == EventKind.EXECUTION_START and kinds[-1] == EventKind.EXECUTION_END
    tool = next(e for e in ex.events if e.name == "bank.withdraw")
    assert tool.source == EventSource.LIVE
    assert tool.destructive is True
    assert tool.parent_event_id is not None  # the model call that requested it
    assert tool.state_before == {"balance": 100} and tool.state_after == {"balance": 50}
    assert tool.duration_ms > 0 and tool.match_key
    assert ex.final_state == {
        "bank": {"balance": 50, "withdrawals": [{"id": "wd_1", "amount": 50}]}
    }
    assert ex.provenance.model_provider == "scripted" and not ex.provenance.model_is_live


def test_replay_is_structurally_identical_to_recording(lab):
    rec = lab.record("toy-bank", "naive", conditions={"bank": "commit_then_timeout"})
    rpl = lab.replay(rec.id)
    assert rpl.status == ExecutionStatus.COMPLETED
    assert rpl.mode == ExecutionMode.REPLAY
    assert _comparable(rpl) == _comparable(rec)  # incl. timestamps, durations, errors
    assert rpl.output == rec.output
    assert diff_executions(rec, rpl).identical
    sources = {e.source for e in rpl.events if e.is_interaction}
    assert sources == {EventSource.RECORDED}
    assert all(
        e.replay and e.replay.verdict == ReplayVerdict.MATCHED
        for e in rpl.events
        if e.is_interaction
    )


def test_replay_twice_is_reproducible(lab):
    rec = lab.record("toy-bank", "safe")
    a, b = lab.replay(rec.id), lab.replay(rec.id)
    assert _comparable(a) == _comparable(b)


def test_replay_never_invokes_tool_handlers_or_model(lab, counters):
    rec = lab.record("toy-bank", "naive")
    assert counters.handler_calls > 0 and counters.model_calls > 0
    counters.handler_calls = counters.model_calls = 0
    lab.replay(rec.id)
    assert counters.handler_calls == 0
    assert counters.model_calls == 0


def test_recorded_errors_are_replayed_with_their_type(lab):
    rec = lab.record("toy-bank", "naive", conditions={"bank": "commit_then_timeout"})
    errs = [e for e in rec.events if e.error]
    assert errs and errs[0].error.type == "ToolTimeout"
    rpl = lab.replay(rec.id)
    assert [e.error.model_dump() for e in rpl.events if e.error] == [
        e.error.model_dump() for e in errs
    ]


def test_nondeterminism_is_recorded_and_replayed(lab):
    rec = lab.record("toy-bank", "safe")
    nd = [e for e in rec.events if e.kind == EventKind.NONDETERMINISM]
    assert {e.name for e in nd} == {"ids.new", "clock.now"}
    rpl = lab.replay(rec.id)
    assert [e.response for e in rpl.events if e.kind == EventKind.NONDETERMINISM] == [
        e.response for e in nd
    ]


def test_offline_guard_blocks_sockets_only_in_guarded_thread():
    with offline_guard(), pytest.raises(OfflineViolation):
        socket.create_connection(("127.0.0.1", 9), timeout=0.1)
    errors: list[BaseException] = []

    def other_thread() -> None:
        try:
            socket.getaddrinfo("localhost", 80)
        except OfflineViolation as exc:  # pragma: no cover - would be a bug
            errors.append(exc)
        except OSError:
            pass

    with offline_guard():
        t = threading.Thread(target=other_thread)
        t.start()
        t.join()
    assert errors == []


def test_agent_network_access_during_replay_fails_loudly(lab, scenario, monkeypatch):
    rec = lab.record("toy-bank", "naive")
    from toy import BankAgent

    original = BankAgent.run

    def sneaky(self, rt, task):  # an agent that tries to phone home
        socket.create_connection(("example.com", 443), timeout=0.1)
        return original(self, rt, task)

    monkeypatch.setattr(BankAgent, "run", sneaky)
    rpl = lab.replay(rec.id)
    assert rpl.status == ExecutionStatus.FAILED
    err = next(e for e in rpl.events if e.kind == EventKind.ERROR)
    assert err.error.type == "OfflineViolation"


# --------------------------------------------------------------------------------------
# Low-level session tests (divergence semantics)
# --------------------------------------------------------------------------------------


def _new_execution(eid: str) -> Execution:
    return Execution(
        id=eid,
        app="t",
        scenario="s",
        variant="v",
        agent="a",
        mode=ExecutionMode.RECORD,
        created_at="2026-01-01T00:00:00+00:00",
        started_at="2026-01-01T00:00:00+00:00",
        provenance=Provenance(
            model_provider="scripted", model="m", model_is_live=False, label="test"
        ),
    )


def _record(calls: list[tuple[str, dict]]) -> Execution:
    ex = _new_execution("ref")
    clock = VirtualClock()
    s = Session(Recorder(ex, clock), mode=ExecutionMode.RECORD, clock=clock)
    for name, args in calls:
        s.interact(Operation(EventKind.TOOL_CALL, name, args), lambda a=args: {"echo": a})
    return ex


def _replay(ref: Execution) -> tuple[Session, Execution]:
    ex = _new_execution("rpl")
    clock = VirtualClock()
    return Session(Recorder(ex, clock), mode=ExecutionMode.REPLAY, clock=clock, reference=ref), ex


def _boom():
    raise AssertionError("invoke must never run during replay")


def test_changed_arguments_are_reported_as_divergence():
    ref = _record([("orders.get", {"id": 1}), ("refund", {"amount": 10})])
    s, ex = _replay(ref)
    assert s.interact(Operation(EventKind.TOOL_CALL, "orders.get", {"id": 1}), _boom)[0] == {
        "echo": {"id": 1}
    }
    with pytest.raises(ReplayDivergenceError) as info:
        s.interact(Operation(EventKind.TOOL_CALL, "refund", {"amount": 20}), _boom)
    div = s.divergence
    assert div.type == "mismatch" and div.recorded_seq == 1
    assert div.changes == [{"path": "amount", "op": "changed", "before": 10, "after": 20}]
    assert "amount" in str(info.value)
    assert ex.events[-1].kind == EventKind.DIVERGENCE
    # Recorded responses are never consumed after divergence.
    with pytest.raises(ReplayDivergenceError):
        s.interact(Operation(EventKind.TOOL_CALL, "refund", {"amount": 10}), _boom)


def test_changed_execution_path_is_reported():
    ref = _record([("a", {}), ("b", {})])
    s, _ = _replay(ref)
    s.interact(Operation(EventKind.TOOL_CALL, "a", {}), _boom)
    with pytest.raises(ReplayDivergenceError):
        s.interact(Operation(EventKind.TOOL_CALL, "c", {}), _boom)
    assert "expected tool_call 'b'" in s.divergence.message


def test_missing_recording_raises():
    ref = _record([("a", {})])
    s, _ = _replay(ref)
    s.interact(Operation(EventKind.TOOL_CALL, "a", {}), _boom)
    with pytest.raises(MissingRecordingError):
        s.interact(Operation(EventKind.TOOL_CALL, "a", {}), _boom)
    assert s.divergence.type == "unexpected_call"


def test_incomplete_replay_is_reported():
    ref = _record([("a", {}), ("b", {})])
    s, _ = _replay(ref)
    s.interact(Operation(EventKind.TOOL_CALL, "a", {}), _boom)
    s.finish()
    assert s.divergence.type == "incomplete"
    assert "1 recorded interaction" in s.divergence.message


def test_replay_requires_reference():
    ex = _new_execution("x")
    clock = VirtualClock()
    with pytest.raises(ValueError):
        Session(Recorder(ex, clock), mode=ExecutionMode.REPLAY, clock=clock)
