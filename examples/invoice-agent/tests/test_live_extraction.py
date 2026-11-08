"""Real LLM extraction (paid API call). Runs only when asked:

INVOICE_AGENT_LIVE=1 ANTHROPIC_API_KEY=... pytest tests/test_live_extraction.py
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("INVOICE_AGENT_LIVE") != "1" or not os.environ.get("ANTHROPIC_API_KEY"),
    reason="set INVOICE_AGENT_LIVE=1 and ANTHROPIC_API_KEY to call the real model",
)


def test_live_model_extracts_fields_and_replay_does_not_call_it():
    from invoice_agent.agent import ghost

    run = ghost.record(agent="fixed")
    extraction = run.model_calls()[0]
    assert extraction.source.value == "live"
    assert extraction.response["amount_cents"] == 12900
    assert extraction.response["extracted_by"].startswith("claude")
    assert run.execution.provenance.model_is_live
    assert ghost.replay(run).live_calls == 0
