# CI integration

Regression cases run fully offline. They need no payment API, no cloud account and no LLM key, so they fit in any CI pipeline. CI fails when a case's outcome doesn't match its expectation, for example when a safety invariant is violated again.

## GitHub Actions

[`examples/github-actions.yml`](examples/github-actions.yml) is a complete workflow for *your* agent's repository:

```yaml
name: agent-regressions
on: [push, pull_request]

jobs:
  ghostreplay:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - name: Install your agent and the GhostReplay SDK
        run: |
          pip install "ghostreplay @ git+https://github.com/thosuperman/ghost-replay@main#subdirectory=packages/ghostreplay"
          pip install -e ".[test]"
      - name: Replay recorded incidents as regression tests
        run: ghostreplay test tests/regression --import invoice_agent.agent --junit reports/ghostreplay.xml
      - name: Unit tests (include the generated test_*.py files)
        run: pytest
```

Replace `invoice_agent.agent` with the module that creates your `GhostReplay` object.

## How to build the case set

1. Reproduce an incident: record it, or inject the fault into a recorded run.
2. Write cases for both agents:
   `ghost.write_regression_test(incident, "tests/regression", agent="buggy", import_module="my_agent.agent")` and the same with `agent="fixed"`.
3. Commit `tests/regression/*.case.json` and `test_*.py`.
4. When you change the agent, CI re-runs every case against the new code and simulated services.

[`examples/invoice-agent/invoice_agent/export_cases.py`](../../examples/invoice-agent/invoice_agent/export_cases.py) does steps 1 and 2 in a single command.

## Sample output

This is the real output of `ghostreplay test tests/regression --import invoice_agent.agent` in `examples/invoice-agent`:

```text
[ok ] [FAIL] Invoice Processing Agent: timeout after commit (buggy) (invoice-agent/buggy, expected FAIL)
  ✘ payments.no_duplicate: INV-2041 was paid 2 times
      why it matters: An invoice is paid at most once
  ✘ payments.amount_matches_invoice: invoiced 12900 cents but paid 25800 cents
      why it matters: The vendor receives exactly the invoiced amount
  ✔ errors.surfaced: Every tool error was recovered or reported.

[ok ] [PASS] Invoice Processing Agent: timeout after commit (fixed) (invoice-agent/fixed, expected PASS)
  ✔ payments.no_duplicate: An invoice is paid at most once
  ✔ payments.amount_matches_invoice: The vendor receives exactly the invoiced amount
  ✔ errors.surfaced: Every tool error was recovered or reported.

2/2 cases matched expectations
```

If someone reintroduces the bug in the fixed agent, the second case reports `[BAD] [FAIL] … expected PASS` and the command exits with 1.

## In this repository

The `sdk` job in this repository's [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) does the same for the invoice example on every push:

1. builds the SDK wheel;
2. installs it into a fresh virtual environment with the example;
3. runs the demo, the committed regression cases, the example's tests and the documented examples.
