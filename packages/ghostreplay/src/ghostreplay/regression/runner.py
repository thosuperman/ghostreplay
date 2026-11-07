"""Run regression cases outside a long-lived lab (pytest, CLI, CI)."""

from __future__ import annotations

from ..lab.lab import Lab
from ..lab.registry import resolve
from ..storage import SqliteStore
from .cases import RegressionCase, RegressionReport


def run_case(case: RegressionCase) -> RegressionReport:
    """Resolve the case's scenario from the registry and run it in an isolated in-memory lab."""
    scenario = resolve(case.scenario)
    lab = Lab(case.app, [scenario], SqliteStore(":memory:"))
    return lab.run_case(case)
