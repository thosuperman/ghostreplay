# Trace import and export

A trace is one run as a JSON document (`<run id>.trace.json`). It contains:

- the run's metadata;
- every recorded event;
- the faults;
- the invariant verdicts;
- the provenance.

Traces are versioned (`"schema_version": "ghostreplay/v1"`) and already redacted.

## Export and load in Python

```python
import json
import tempfile

from ghostreplay import GhostReplay

ghost = GhostReplay("exporter")


@ghost.tool("echo")
def echo(text: str) -> dict:
    return {"text": text}


@ghost.agent()
def agent(task: dict) -> str:
    return echo(task["text"])["text"]


run = ghost.record({"text": "hi"})
out = tempfile.mkdtemp()
path = ghost.export(run, out)
doc = json.loads(path.read_text())
print(path.name, doc["schema_version"], len(doc["events"]))

# Elsewhere (another process or machine) with the same agent code:
fresh = GhostReplay("exporter")
fresh.tool("echo")(echo.__wrapped__)  # the same tool names as the recording
fresh.agent()(agent)
loaded = fresh.load(path)  # validated, stored; nothing in it is executed
again = fresh.replay(loaded)
print(loaded.id == run.id, again.status, again.live_calls)  # True completed 0
```

## Command line

```bash
ghostreplay export RUN_ID --store ./ghostreplay-data --app my-agent --out traces/
ghostreplay inspect traces/RUN_ID.trace.json            # human-readable
ghostreplay inspect traces/RUN_ID.trace.json --json     # machine-readable summary
ghostreplay diff traces/A.trace.json traces/B.trace.json [--json] [--fail-on-diff]
ghostreplay replay traces/RUN_ID.trace.json --app my_agent.agent:ghost
```

## Safety guarantees on import

Loading a trace, whether from the CLI, `ghost.load`, the regression runner or the dashboard, treats it as untrusted data:

- **Size:** at most 20 MB from the CLI and SDK, and 512 KiB on the public dashboard.
- **Schema:** the document is validated against the trace schema. Unknown fields are rejected (`extra="forbid"`). The schema version must match. Event `seq` numbers must be strictly increasing and event ids unique.
- **No executable content:** traces are parsed with pydantic from JSON only. There's no pickle, no YAML, no `eval` and no dynamic imports. A trace can only name an app or scenario; it can never point at code. Errors are rebuilt from an allowlist of error types.
- **No arbitrary paths:** file names are checked against a strict pattern and resolved inside the target directory, so `../` and absolute paths are rejected.
- **Compatibility:** `ghost.load` refuses a trace from a different app. The engine refuses an unsupported `schema_version`.

## Replaying an imported trace

A trace is not a program. To replay it you need the agent code that produced it, and that code must be instrumented with the same tool and model names. `ghostreplay replay` asks for that code explicitly with `--app module:attribute`.

## In the hosted dashboard

<https://ghostreplay.hayaix.tech/#/import> accepts a trace file for inspection: timeline, events, faults and verdicts.

- **Validation:** the server validates the upload, redacts it again, and caps its size (512 KiB) and its event count (5,000).
- **Storage:** it's stored only in your browser session and deleted after 24 hours, and uploads are rate-limited.
- **Replay:** the hosted server never runs your code. Traces from the two demo labs can be replayed there; a trace from your own app can only be replayed on your machine.
- **Download:** each run in the dashboard can be downloaded with `GET /lab/<lab>/api/executions/<id>/trace`.
