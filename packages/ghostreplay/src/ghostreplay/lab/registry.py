"""Scenario registry.

Scenarios are resolved by id from (a) scenarios registered in-process and (b) Python entry
points in the ``ghostreplay.scenarios`` group declared by installed packages. A trace or case
file can only *name* a scenario id; it can never point at code to import.
"""

from __future__ import annotations

from importlib.metadata import entry_points

from ..core.errors import ScenarioNotFound
from .scenario import Scenario

ENTRY_POINT_GROUP = "ghostreplay.scenarios"
_registered: dict[str, Scenario] = {}


def register(scenario: Scenario) -> Scenario:
    _registered[scenario.id] = scenario
    return scenario


def available() -> dict[str, Scenario]:
    found = dict(_registered)
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        if ep.name in found:
            continue
        factory = ep.load()
        scenario = factory() if callable(factory) else factory
        if not isinstance(scenario, Scenario):
            continue
        found[scenario.id] = scenario
    return found


def resolve(scenario_id: str) -> Scenario:
    if scenario_id in _registered:
        return _registered[scenario_id]
    scenarios = available()
    if scenario_id not in scenarios:
        raise ScenarioNotFound(
            f"scenario {scenario_id!r} is not registered (available: {', '.join(sorted(scenarios)) or 'none'})"
        )
    return scenarios[scenario_id]
