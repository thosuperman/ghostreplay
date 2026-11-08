# Design — Python SDK and guided experience

## SDK (`packages/ghostreplay/src/ghostreplay/sdk.py`)

`GhostReplay` wraps the existing engine; it adds no new replay logic.

- **Scenario adapter.** An internal `_SdkScenario` implements the `Scenario` interface from the
  registered tools, agents, invariants and the `@ghost.state` / `@ghost.reset` hooks. A `Lab`
  over a `SqliteStore` runs it, so record, replay, counterfactual, diff and regression are the
  same code paths the bundled labs use.
- **Routing.** A `ContextVar` holds the active run's `AgentRuntime`. Decorated functions route
  through `rt.call_tool` or `session.interact` when a run is active, and call the original
  function otherwise.
- **Agents.** `_FunctionAgent` adapts `fn(task) -> dict | str | AgentResult`. Async functions
  run on a private loop in a worker thread with the caller's context.
- **Registration.** Constructing `GhostReplay` registers its scenario by app name, so
  `run_case` and generated tests resolve it after the app module is imported.
- **Engine additions.** `Lab.record(task=...)` and `RegressionCase.task` let SDK apps pass
  their own inputs. Bundled-lab cases omit the task when it equals the scenario default.

## Server additions (`server/app.py`)

- `GET /api/executions/{id}/trace` downloads a run, scoped to the session.
- `POST /api/traces/import` uses `parse_document`, then `redact_execution`, then an
  event-count cap, then a save into the owned store (`OwnershipConflict` returns 409).
- `GET /api/executions?imported=true` lists this session's runs from other apps.

## Dashboard

- **Routes:** `#/demo/{refund,devops}`, `#/connect` and `#/import`. The pretty paths
  `/demo/...`, `/connect` and `/import` are served the SPA by Caddy and the gateway, and
  rewritten to the hash routes.
- **Guided demos:** `views/guided/demos.ts` holds the copy plus pure functions that derive
  facts, story lines and comparison rows from `Execution` objects. `views/GuidedDemo.tsx`
  drives the existing API.
- **Tested code:** `Home` and `Connect` import `docs/sdk/examples/*.py` and the CI example via
  Vite `?raw`, so the code shown is the tested file.
