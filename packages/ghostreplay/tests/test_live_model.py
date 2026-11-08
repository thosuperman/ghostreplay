"""Live-LLM mode, exercised against a fake Messages API client (no network, no key).

The fake returns SDK-shaped objects, so the adapter's request building, response parsing,
recording and offline replay are tested for real; only the HTTP call is replaced.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from ghostreplay.lab import Lab
from ghostreplay.llm import LiveModelConfig
from ghostreplay.llm.anthropic_adapter import (
    AnthropicModel,
    LiveModelError,
    decode_tool_name,
    encode_tool_name,
    from_response,
    to_messages,
)
from ghostreplay.mocking import Message, ModelRequest, ToolCallRequest
from ghostreplay.models import EventKind, ExecutionStatus
from ghostreplay.storage import SqliteStore

SC = "toy-bank"


def _msg(blocks: list[dict[str, Any]], stop: str, model: str = "claude-opus-5-5"):
    return SimpleNamespace(
        content=[dict(b) for b in blocks],
        stop_reason=stop,
        model=model,
        usage=SimpleNamespace(model_dump=lambda **_: {"input_tokens": 120, "output_tokens": 30}),
    )


THINKING = {"type": "thinking", "thinking": "", "signature": "sig-abc"}
SCRIPT = [
    _msg(
        [
            THINKING,
            {
                "type": "tool_use",
                "id": "tu_1",
                "name": "bank__balance",
                "input": {"account": "acc-1"},
            },
        ],
        "tool_use",
    ),
    _msg(
        [
            {
                "type": "tool_use",
                "id": "tu_2",
                "name": "bank__withdraw",
                "input": {"account": "acc-1", "amount": 50},
            }
        ],
        "tool_use",
    ),
    _msg([{"type": "text", "text": "Withdrew 50."}], "end_turn"),
]


class FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **params: Any) -> Any:
        self.requests.append(copy.deepcopy(params))
        if not self.responses:
            raise AssertionError("fake client called more often than scripted")
        return self.responses.pop(0)


@dataclass(frozen=True)
class FakeLive(LiveModelConfig):
    client: Any = None

    def build(self, *, model: str | None = None) -> AnthropicModel:
        return AnthropicModel(
            model or self.model, effort=self.effort, max_calls=self.max_calls, client=self.client
        )


@pytest.fixture
def fake() -> FakeClient:
    return FakeClient(SCRIPT)


@pytest.fixture
def live_lab(scenario, fake) -> Lab:
    return Lab("toy", [scenario], SqliteStore(":memory:"), live=FakeLive(client=fake))


# -- configuration --------------------------------------------------------------------------


def test_live_mode_is_off_unless_explicitly_enabled():
    assert LiveModelConfig.from_env({}) is None
    assert LiveModelConfig.from_env({"ANTHROPIC_API_KEY": "x"}) is None
    cfg = LiveModelConfig.from_env({"GHOSTREPLAY_LIVE": "1", "GHOSTREPLAY_LIVE_EFFORT": "low"})
    assert cfg is not None and cfg.model == "claude-opus-5-5" and cfg.effort == "low"
    with pytest.raises(ValueError, match="effort"):
        LiveModelConfig.from_env({"GHOSTREPLAY_LIVE": "1", "GHOSTREPLAY_LIVE_EFFORT": "huge"})
    with pytest.raises(ValueError, match="provider"):
        LiveModelConfig.from_env({"GHOSTREPLAY_LIVE": "1", "GHOSTREPLAY_LIVE_PROVIDER": "x"})


def test_scripted_lab_refuses_live_runs(lab):
    with pytest.raises(ValueError, match="live AI mode is not enabled"):
        lab.record(SC, "naive", model="live")


# -- request / response mapping -----------------------------------------------------------


def test_tool_names_are_encoded_reversibly():
    assert encode_tool_name("payments.create_refund") == "payments__create_refund"
    assert decode_tool_name("payments__create_refund") == "payments.create_refund"
    with pytest.raises(LiveModelError):
        encode_tool_name("has space")


def test_tool_results_are_grouped_into_one_user_turn():
    msgs = [
        Message(role="user", content="hi"),
        Message(
            role="assistant",
            tool_calls=[
                ToolCallRequest(id="a", name="x.one", arguments={}),
                ToolCallRequest(id="b", name="x.two", arguments={"k": 1}),
            ],
        ),
        Message(role="tool", tool_call_id="a", name="x.one", data={"ok": 1}),
        Message(role="tool", tool_call_id="b", name="x.two", data={"error": "Timeout"}),
    ]
    out = to_messages(msgs)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert [b["name"] for b in out[1]["content"]] == ["x__one", "x__two"]
    results = out[2]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b"]
    assert [r["is_error"] for r in results] == [False, True]


def test_provider_blocks_are_echoed_and_fallback_boundary_respected():
    blocks = [
        {"type": "thinking", "thinking": "", "signature": "s1"},
        {"type": "text", "text": "partial"},
        {"type": "fallback", "from": {"model": "a"}, "to": {"model": "b"}},
        {"type": "thinking", "thinking": "", "signature": "s2"},
        {"type": "tool_use", "id": "t", "name": "x__y", "input": {}},
    ]
    out = to_messages(
        [Message(role="user", content="q"), Message(role="assistant", provider_content=blocks)]
    )
    echoed = out[1]["content"]
    assert [b["type"] for b in echoed] == ["text", "thinking", "tool_use"]
    assert echoed[1]["signature"] == "s2"


def test_refusal_is_an_error_not_a_silent_success():
    with pytest.raises(LiveModelError, match="refusal"):
        from_response(_msg([], "refusal"))


def test_call_budget_is_enforced():
    model = AnthropicModel("m", max_calls=1, client=FakeClient(SCRIPT))
    req = ModelRequest(model="m", messages=[Message(role="user", content="q")])
    model.complete(req)
    with pytest.raises(LiveModelError, match="budget"):
        model.complete(req)


# -- end to end through the Lab -----------------------------------------------------------


def test_live_run_is_recorded_with_provenance_and_native_requests(live_lab, fake, counters):
    rec = live_lab.record(SC, "naive", model="live")
    assert rec.status == ExecutionStatus.COMPLETED
    assert rec.output.message == "Withdrew 50."
    assert rec.provenance.model_is_live and rec.provenance.model_provider == "anthropic"
    calls = [e for e in rec.events if e.kind == EventKind.MODEL_CALL]
    assert [e.name for e in calls] == ["claude-opus-5-5"] * 3
    assert calls[0].response["served_by"] == "claude-opus-5-5"
    assert counters.model_calls == 0  # the scripted toy policy was never consulted

    first, second = fake.requests[0], fake.requests[1]
    assert first["model"] == "claude-opus-5-5"
    assert first["output_config"] == {"effort": "medium"}
    assert first["fallbacks"] == "default"
    assert {t["name"] for t in first["tools"]} >= {"bank__balance", "bank__withdraw"}
    # The thinking block from turn 1 is passed back unchanged on turn 2.
    assert second["messages"][1]["content"][0] == THINKING
    assert second["messages"][2]["content"][0]["type"] == "tool_result"


def test_live_recording_replays_offline_without_calling_the_api(live_lab, fake):
    rec = live_lab.record(SC, "naive", model="live")
    sent = len(fake.requests)
    rpl = live_lab.replay(rec.id)
    assert rpl.status == ExecutionStatus.COMPLETED
    assert len(fake.requests) == sent
    assert rpl.provenance.model_is_live and rpl.provenance.model == "claude-opus-5-5"
    assert rpl.provenance.tool_backends.startswith("none")


def test_reexecuting_a_live_capture_without_credentials_reuses_its_decisions(live_lab, scenario):
    rec = live_lab.record(SC, "naive", model="live")
    calls_before = len(live_lab.live.client.requests)
    offline_only = Lab("toy", [scenario], live_lab.store)  # no live config at all
    again = offline_only.reexecute(rec.id)
    assert again.mode.value == "branch" and again.status == ExecutionStatus.COMPLETED
    model_events = [e for e in again.events if e.kind.value == "model_call"]
    assert model_events and all(e.source.value == "recorded" for e in model_events)
    tool_events = [e for e in again.events if e.kind.value == "tool_call"]
    assert tool_events and all(e.source.value == "simulated" for e in tool_events)
    assert "genuine capture" in again.provenance.label and not again.provenance.model_is_live
    assert len(live_lab.live.client.requests) == calls_before  # no new provider request


def test_leaving_the_captured_path_without_live_mode_fails_loudly(live_lab, scenario):
    rec = live_lab.record(SC, "naive", model="live")
    offline_only = Lab("toy", [scenario], live_lab.store)
    branched = offline_only.counterfactual(rec.id, [], variant="safe", mode="branch")
    assert branched.status == ExecutionStatus.FAILED
    assert any(e.error and "needs a new model decision" in e.error.message for e in branched.events)


def test_budget_exhaustion_fails_the_run_loudly(scenario):
    lab = Lab("toy", [scenario], live=FakeLive(client=FakeClient(SCRIPT), max_calls=1))
    ex = lab.record(SC, "naive", model="live")
    assert ex.status == ExecutionStatus.FAILED
    errors = [e for e in ex.events if e.error is not None]
    assert any("budget" in (e.error.message or "") for e in errors)
