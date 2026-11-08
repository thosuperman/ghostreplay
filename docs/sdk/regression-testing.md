# Regression testing

Once you have a run that shows a bug, turn it into a test that:

- **fails** for the buggy agent, which proves the safety invariant detects the bug;
- **passes** for the fixed agent, which proves the fix holds under the same conditions.

```python
import tempfile
from pathlib import Path

from ghostreplay import GhostReplay, ToolTimeout, TraceView, fault

ghost = GhostReplay("refunder")
REFUNDS: list[int] = []


@ghost.reset
def reset() -> None:
    REFUNDS.clear()


@ghost.state
def state() -> dict:
    return {"refunds": list(REFUNDS)}


@ghost.tool("payments.refund", destructive=True)
def refund(amount: int, key: str | None = None) -> dict:
    REFUNDS.append(amount)
    return {"ok": True}


@ghost.tool("payments.list")
def list_refunds() -> list:
    return list(REFUNDS)


@ghost.agent("buggy")
def buggy(task: dict) -> dict:
    for _ in range(2):
        try:
            refund(task["amount"])
            return {"status": "success", "message": "refunded"}
        except ToolTimeout:
            continue
    return {"status": "failed", "message": "gave up"}


@ghost.agent("fixed", fix=True)
def fixed(task: dict) -> dict:
    try:
        refund(task["amount"], ghost.new_id("rf"))
    except ToolTimeout:
        if not list_refunds():  # check before retrying
            refund(task["amount"], ghost.new_id("rf"))
    return {"status": "success", "message": "refunded"}


@ghost.invariant("refunds.once", requires_state=True)
def once(view: TraceView) -> bool | str:
    n = len(view.final_state["refunds"])
    return n <= 1 or f"{n} refunds issued"


incident = ghost.record(
    {"amount": 129}, agent="buggy", faults=[fault("timeout_after_commit", "payments.refund")]
)

for agent in ("buggy", "fixed"):
    report = ghost.check(ghost.regression_case(incident, agent=agent))
    print(report.explain())
    assert report.outcome_matches_expectation

out = Path(tempfile.mkdtemp())
case_path, test_path = ghost.write_regression_test(
    incident, out, agent="fixed", import_module="my_agent.agent"
)
print(test_path.read_text().splitlines()[12:16])
```

## What a case contains

A `.case.json` file is plain, validated data. It is never executed. It contains:

- the app (scenario) name;
- which agent to run;
- the task;
- the faults;
- optionally a reference trace, for branch-mode cases built from counterfactuals;
- `expect: "pass" | "fail"`.

Running a case re-executes the named agent of the registered app under exactly those inputs and faults, against your simulated services. It then evaluates the invariants. `expect` defaults to `"pass"` for agents registered with `fix=True`.

## The generated pytest module

```python
# fragment
from pathlib import Path

import my_agent.agent  # noqa: F401  (registers the GhostReplay app)

from ghostreplay.regression import load_case, run_case

CASE_FILE = Path(__file__).with_name("refunder-timeout-after-commit-fixed.case.json")


def test_refunder_timeout_after_commit_fixed() -> None:
    report = run_case(load_case(CASE_FILE))
    print(report.explain())
    assert report.outcome_matches_expectation, report.explain()
```

`import_module` must be the module that creates your `GhostReplay` object, so the app is registered when pytest imports the test. Commit both files. They run offline with plain `pytest`.

## Running cases without pytest

```bash
ghostreplay test tests/regression --import my_agent.agent --junit reports/ghostreplay.xml --json reports/ghostreplay.json
```

It prints each report and exits with 1 if any case's outcome does not match its expectation. A buggy case that passes counts as a mismatch too, because it means the detector no longer catches the bug.
