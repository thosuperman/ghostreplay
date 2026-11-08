"""Real provider integration. Makes paid API calls, so it only runs when asked:

    set -a; . ./.env; set +a
    GHOSTREPLAY_LIVE_TESTS=1 GHOSTREPLAY_LIVE=1 uv run pytest tests/live -o addopts="" -v

Unlike the rest of the suite (scripted model or recorded captures), this proves that a live
model chooses the tools and that its decisions drive real HTTP and SQL side effects.
"""

from __future__ import annotations

import os

import pytest

from ghostreplay.llm import LiveModelConfig
from ghostreplay.storage import SqliteStore
from support_agent.cli import build_lab

pytestmark = pytest.mark.skipif(
    not (os.environ.get("GHOSTREPLAY_LIVE_TESTS") == "1" and os.environ.get("ANTHROPIC_API_KEY")),
    reason="live provider test: set GHOSTREPLAY_LIVE_TESTS=1, GHOSTREPLAY_LIVE=1 and ANTHROPIC_API_KEY",
)


def test_live_model_chooses_tools_that_cause_real_side_effects():
    live = LiveModelConfig.from_env()
    assert live is not None, "GHOSTREPLAY_LIVE=1 is required"
    lab = build_lab(SqliteStore(":memory:"))
    lab.live = live
    sc = lab.scenario("duplicate-refund")
    ex = lab.record(sc.id, "vulnerable", conditions=sc.incident_conditions(), model="live")

    models = [e for e in ex.events if e.kind.value == "model_call"]
    assert models and all(e.source.value == "live" for e in models)
    assert all(e.response.get("served_by") for e in models)  # answered by the provider
    chosen = [c["name"] for e in models for c in e.response.get("tool_calls", [])]
    assert "orders.lookup_order" in chosen and "payments.create_refund" in chosen
    # The model's decision reached the real refund service and the database.
    assert ex.final_state["evidence"]["http_requests_received"] >= 1
    assert ex.final_state["payments"]["refunds"], "no refund was committed"
    # Offline replay of the live run makes no provider call.
    rpl = lab.replay(ex.id)
    assert rpl.status.value == "completed"
    assert all(e.source.value == "recorded" for e in rpl.events if e.kind.value == "model_call")
