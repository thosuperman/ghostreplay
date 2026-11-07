"""The documented example must keep working."""

from __future__ import annotations

import runpy
from pathlib import Path


def test_minimal_agent_example(capsys):
    runpy.run_path(
        str(Path(__file__).parents[1] / "examples" / "minimal_agent.py"), run_name="__main__"
    )
    out = capsys.readouterr().out
    assert "identical to recording = True" in out
    assert "[FAILED] errors.surfaced" in out
