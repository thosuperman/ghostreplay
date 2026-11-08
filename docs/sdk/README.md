# GhostReplay Python SDK

Instrument your own Python agent and record, replay, break and regression-test it. Every
runnable code block in these pages is executed by `tests/test_sdk_docs.py`.

| Page | What it covers |
|---|---|
| [Quickstart](quickstart.md) | Install, record, replay and prove a fix in five minutes |
| [Installation](installation.md) | GitHub, checkout and wheel installs; extras |
| [Python API](python-api.md) | `GhostReplay`, `Run`, `fault`, invariants and errors |
| [Instrumentation](instrumentation.md) | What is recorded, what is not, and the rules |
| [Model adapters](model-adapters.md) | `@ghost.model`, `ModelAdapter` and `ghost.complete`, live LLMs, labels |
| [Tool wrapping](tool-wrapping.md) | `@ghost.tool` options, matching and async |
| [Recording](recording.md) | Runs, storage, redaction, state |
| [Replay](replay.md) | Strict offline replay, divergence, replay vs re-execution |
| [Failure injection](failure-injection.md) | The 15 fault kinds and three ways to inject them |
| [Regression testing](regression-testing.md) | Cases, generated pytest modules, `ghostreplay test` |
| [Trace import/export](trace-import-export.md) | Trace files, the CLI and import safety |
| [CI integration](ci-integration.md) | GitHub Actions with real sample output |
| [Limitations](limitations.md) | What the SDK does not do, plus common errors |

Examples: [`examples/hello.py`](examples/hello.py), [`examples/quickstart.py`](examples/quickstart.py),
and a complete separate app in [`examples/invoice-agent`](../../examples/invoice-agent/README.md).
