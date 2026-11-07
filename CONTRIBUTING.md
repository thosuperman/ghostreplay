# Contributing to GhostReplay Lab

Thanks for your interest in GhostReplay Lab. This document explains how to set up a
development environment, which checks a change must pass, and how to extend the framework
with new scenarios, faults and invariants.

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Security
issues are **not** reported through public issues: see [SECURITY.md](SECURITY.md).

## Repository layout

| Path | What it is |
|---|---|
| `packages/ghostreplay/` | The shared framework (runtime, session, recorder, mutation, diff, regression, storage, server) and its guarantee tests |
| `apps/support-agent/` | Support Agent Lab: the Duplicate Refund scenario |
| `apps/devops-agent/` | DevOps Agent Lab: the Unsafe Infrastructure Action scenario |
| `apps/dashboard/` | React + TypeScript dashboard, plus Playwright end-to-end tests in `e2e/` |
| `tests/` | Generated regression cases, deployment and example tests |
| `examples/` | Bring-your-own-agent example |
| `docs/` | Architecture, demo script, deployment and live AI documentation |
| `.kiro/` | Steering documents, specs and agent hooks |

## Development setup

Prerequisites:

- Python 3.12 or newer (the repository pins 3.13 in `.python-version`; CI and the container use 3.13)
- [uv](https://docs.astral.sh/uv/) (CI pins 0.13.7)
- Node.js 20 or newer (CI and the container use Node 24) with `corepack`, which provides the
  pinned pnpm version from `package.json`

```bash
uv sync                      # Python workspace: framework + both labs + dev tools
```

```bash
corepack pnpm install        # dashboard dependencies
```

Optional, only if you work on the live LLM adapter:

```bash
uv sync --extra live
```

Start everything (both lab APIs and the dashboard dev server):

```bash
./scripts/dev.sh
```

Then open http://127.0.0.1:5173. The lab APIs listen on :8101 (support) and :8102 (devops).
To run the single-process gateway instead (both labs plus the built dashboard on one port):

```bash
corepack pnpm --dir apps/dashboard build && uv run ghostreplay serve --port 8100
```

No API keys, cloud accounts or network services are needed for development. Every tool is
an in-memory simulation and the demo agents use scripted models.

## Checks every change must pass

These are the same commands CI runs (`.github/workflows/ci.yml`).

| Check | Command |
|---|---|
| Lint | `uv run ruff check .` |
| Formatting | `uv run ruff format --check .` (fix with `uv run ruff format .`) |
| Python tests | `uv run pytest` |
| Terminal demos | `uv run support-agent-lab --db "$TMPDIR/gr-dev" demo` and `uv run devops-agent-lab --db "$TMPDIR/gr-dev" demo` |
| Regression cases | `uv run ghostreplay test tests/regression --junit reports/junit.xml --json reports/report.json` |
| Dashboard typecheck | `corepack pnpm --dir apps/dashboard typecheck` |
| Dashboard build | `corepack pnpm --dir apps/dashboard build` |
| End-to-end | `corepack pnpm --dir apps/dashboard e2e` |

The end-to-end suite builds the dashboard, starts `ghostreplay serve` on a fresh store and
drives it with Playwright. Install the browser once:

```bash
corepack pnpm --dir apps/dashboard exec playwright install chromium
```

If you changed the container setup, also check that the image builds and passes its health
check:

```bash
docker compose up --build
```

```bash
curl -fsS http://127.0.0.1:8100/api/health
```

## Extending the framework

### Add a scenario (or a new lab)

A scenario plugs an agent into GhostReplay. Use `examples/minimal_agent.py` as the smallest
complete reference and the two apps as full examples.

1. Create a package under `apps/<your-lab>/` with its own `pyproject.toml` that depends on
   `ghostreplay`, and add it to `[tool.uv.workspace].members` in the root `pyproject.toml`.
2. Subclass `ghostreplay.lab.scenario.Scenario` and implement `default_task`,
   `build_environment` (simulated backends and an allowlisted `ToolRegistry`),
   `build_model` (a `ModelAdapter`, usually a `ScriptedModel`), `build_agent(variant)` and
   `invariants`. Declare at least one vulnerable and one fixed `Variant` (`is_fix=True`),
   any `Condition`s, and optionally `fault_presets`.
3. Make the agent reach the world only through `AgentRuntime` (`rt.complete`,
   `rt.call_tool`, `rt.now`, `rt.new_id`, `rt.random`). Anything that bypasses the runtime
   cannot be replayed and is blocked during offline replay.
4. Register the scenario in your `pyproject.toml`:

   ```toml
   [project.entry-points."ghostreplay.scenarios"]
   my-scenario = "my_lab.scenario:MyScenario"

   [project.entry-points."ghostreplay.labs"]
   mylab = "my_lab.cli:build_lab"
   ```

   The `ghostreplay.labs` entry point lets `ghostreplay serve` mount the lab automatically.
   The dashboard currently knows the two built-in labs by id (`apps/dashboard/src/api/client.ts`
   and the dev proxy in `apps/dashboard/vite.config.ts`); a new lab needs an entry there too.
5. Add tests next to the app (see `apps/*/tests/`): the vulnerable variant must FAIL its
   headline invariant under the headline fault and the fixed variant must PASS.
6. Regenerate regression cases if relevant:
   `uv run <your-lab-cli> export-cases --out tests/regression`.

All tools must be simulations. Do not add real SDK clients (payment, cloud, HTTP clients
pointed at real services) to scenarios or fixtures.

### Add a fault kind

1. Add a `FaultKind` to `_KINDS` in `packages/ghostreplay/src/ghostreplay/mutation/catalog.py`
   with an id, title, description, strategy (`error`, `transform`, `execute_then_error`,
   `delay`) and `requires_branch`. A fault that needs a real side effect to have happened
   must set `requires_branch=True`; never fake a committed side effect in offline replay.
2. Implement its behaviour in `packages/ghostreplay/src/ghostreplay/mutation/faults.py`
   (`_make_error` or `_transform`, or the strategy branch in `apply_fault`). The original
   response must stay on the event (`fault.original_response`).
3. Add default parameters for the Failure Lab form in `apps/dashboard/src/views/FailureLab.tsx`.
4. Add tests in `packages/ghostreplay/tests/test_mutation.py`, and update the catalog table
   in `docs/architecture.md` and the fault count in `README.md`.

### Add an invariant

Invariants live with the app that owns them (`apps/*/src/*/invariants.py`) and are built
from `ghostreplay.regression.Invariant`:

- `check(view: TraceView) -> Check` returns `Check.ok(...)`, `Check.fail(..., evidence, explanation)`
  or `Check.unknown(...)`.
- Cite evidence event ids so the dashboard can highlight them.
- Set `requires_state=True` if the check needs the final simulated state. Such invariants are
  reported as `inconclusive` for strict offline counterfactuals, never silently passed.
- Add the invariant to the scenario's `invariants()` and cover both outcomes in tests.

### Schema changes

The execution schema (`packages/ghostreplay/src/ghostreplay/models/`) is mirrored by
`apps/dashboard/src/api/types.ts`. Update both in the same change and keep stored data
backward compatible, or bump the schema version.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <summary>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`.
Scopes used in this repository include `core`, `replay`, `mutation`, `diff`, `regression`,
`server`, `llm`, `support`, `devops`, `dashboard`, `deploy` and `docs`. Examples:

```
fix(replay): report divergence when a tool name changes mid-run
feat(mutation): add a partial_success fault for batch operations
docs(deploy): document the Render free-tier disk limitation
```

## Pull requests

- Keep a pull request focused on one change and describe what changed, why, and how you
  tested it. The pull request template has a checklist.
- All CI jobs (Python, dashboard, end-to-end and container) must be green.
- Add or update tests for every behaviour change. Framework guarantees (deterministic replay,
  divergence detection, offline guard, redaction, fault semantics) must stay covered.
- Update the relevant docs (`README.md`, `docs/`) and `CHANGELOG.md` under `[Unreleased]`.
- Never commit secrets, `.env` files, real customer data or real credentials, even in
  fixtures. Recordings and case files are redacted, but review them before committing.
- Never add code that performs real side effects (real payments, real cloud calls).
- Label scripted behaviour as scripted. Do not present simulated or counterfactual results
  as real recordings or as live model output.

## Licensing

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
New third-party dependencies must use a license compatible with MIT and be added to
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
