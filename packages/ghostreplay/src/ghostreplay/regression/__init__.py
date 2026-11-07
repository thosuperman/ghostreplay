from .cases import RegressionCase, RegressionReport, load_case
from .generate import pytest_source, reports_to_json, reports_to_junit, write_case
from .invariants import (
    Check,
    Invariant,
    TraceView,
    errors_surfaced,
    evaluate_all,
    max_successful_calls,
)


def run_case(case: RegressionCase) -> RegressionReport:
    from .runner import run_case as _run

    return _run(case)


__all__ = [
    "Check",
    "Invariant",
    "RegressionCase",
    "RegressionReport",
    "TraceView",
    "errors_surfaced",
    "evaluate_all",
    "load_case",
    "max_successful_calls",
    "pytest_source",
    "reports_to_json",
    "reports_to_junit",
    "run_case",
    "write_case",
]
