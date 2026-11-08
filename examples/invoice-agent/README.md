# Invoice Processing Agent: an external GhostReplay app

A separate Python project that uses **only the public GhostReplay SDK**. It doesn't import
anything from the bundled Support or DevOps labs. It shows that GhostReplay can be adopted by
any Python agent.

**The scenario.** The agent reads an invoice (a deterministic `@ghost.model` function stands
in for an LLM), checks the vendor, and pays it through a simulated payment service. The
payment commits but the response times out.

- The **buggy** agent retries blindly and pays the vendor twice.
- The **fixed** agent pays once. It uses an idempotency key and checks the ledger before
  retrying.

All payments are simulated in memory.

## Run it

```bash
cd examples/invoice-agent
pip install ../../packages/ghostreplay -e ".[test]"   # or: pip install "ghostreplay @ git+https://github.com/thosuperman/ghost-replay@main#subdirectory=packages/ghostreplay" -e ".[test]"
invoice-agent-demo                                     # the whole workflow, step by step
pytest                                                 # unit tests + generated regression tests
ghostreplay test tests/regression --import invoice_agent.agent
```

`invoice-agent-demo` walks through seven steps, and every number it prints comes from a
recorded execution:

1. Record a normal run: one payment, every invariant passes.
2. Inject `timeout_after_commit` into `payments.pay`: the vendor receives $258.00 for a $129.00 invoice.
3. Identify the bad call: the first `payments.pay` raised a timeout after committing.
4. Replay the incident offline: identical, with 0 live calls. The payment service is not called.
5. Run the fixed agent under the same fault: $129.00 paid.
6. Compare: the first divergence is the `idempotency_key` argument.
7. Write regression tests for both agents and run them: buggy gives FAIL (expected), fixed gives PASS (expected).

## Files

| File | What it is |
|---|---|
| `invoice_agent/agent.py` | The instrumented agent: `@ghost.model`, `@ghost.tool`, two agents, invariants |
| `invoice_agent/payments.py` | The simulated payment service (in memory) |
| `invoice_agent/demo.py` | The step-by-step demo (`invoice-agent-demo`) |
| `invoice_agent/export_cases.py` | Records the incident and writes `tests/regression/` |
| `tests/test_invoice_agent.py` | Unit tests written against the SDK |
| `tests/regression/` | Generated regression cases and pytest modules (committed) |

The repository's CI installs the built SDK wheel and this project into a fresh virtual
environment and runs all of the above (the `sdk` job).
