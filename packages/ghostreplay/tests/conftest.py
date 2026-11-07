from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from toy import COUNTERS, ToyBankScenario

from ghostreplay.lab import Lab, register
from ghostreplay.storage import SqliteStore


@pytest.fixture
def scenario() -> ToyBankScenario:
    sc = ToyBankScenario()
    register(sc)
    return sc


@pytest.fixture
def lab(scenario: ToyBankScenario) -> Lab:
    return Lab("toy", [scenario], SqliteStore(":memory:"))


@pytest.fixture
def counters():
    COUNTERS.handler_calls = 0
    COUNTERS.model_calls = 0
    return COUNTERS
