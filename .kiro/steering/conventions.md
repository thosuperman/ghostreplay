---
inclusion: fileMatch
fileMatchPattern: ["**/*.py", "**/*.ts", "**/*.tsx"]
---

# Coding conventions

## Python
- Type hints everywhere; `from __future__ import annotations` at the top of every module
  (package `__init__.py` re-export files excepted).
- Pydantic models for data that crosses a boundary (storage, HTTP, trace and case files);
  dataclasses for internal value objects (`ToolSpec`, `FaultKind`, `Invariant`, `Check`).
- Parse untrusted input with `ghostreplay.storage.parsing.parse_document`, not ad-hoc
  `json.loads` + `model_validate`.
- Errors: raise specific exceptions from `ghostreplay.core.errors`. Never `except Exception:
  pass`. Framework errors (`GhostReplayError`) must never be swallowed by agent code; tool
  errors visible to agents are `ToolError` subclasses (register new ones with
  `register_error_type`).
- Public framework functions get a docstring stating the guarantee they provide.
- Tests live next to what they test (`packages/ghostreplay/tests`, `apps/*/tests`,
  repository-level `tests/`). Name tests after the guarantee, e.g.
  `test_replay_never_invokes_tool_handlers_or_model`. Framework tests use the `toy-bank`
  scenario from `packages/ghostreplay/tests/toy.py` and the `lab`/`counters` fixtures.
- Prefer driving the real engine (`Lab`, `Session`, `SqliteStore(":memory:")`) over mocks.
- Ruff clean: `uv run ruff check . && uv run ruff format --check .` (line length 100).

## TypeScript / React
- `strict: true`, `noUncheckedIndexedAccess`; no `any` in application code (use `unknown` and
  narrow).
- `apps/dashboard/src/api/types.ts` mirrors the Pydantic schema field for field
  (`Optional[X]` → `X | null`). Keep it in sync whenever `ghostreplay/models` changes.
- All HTTP calls go through `src/api/client.ts` (`api.*`); views never call `fetch` directly
  (the SSE `EventSource` in Replay Studio takes its URL from `api.replayStreamUrl`).
- Components are small and presentational; shared UI lives in `src/components/ui.tsx`.
- Tailwind utility classes; colour tokens defined once in `src/index.css`.
- Status colours: success = emerald, warning = amber, failure = rose, injected = fuchsia,
  replay/recorded = cyan, accent = violet.
- Verify with `corepack pnpm --dir apps/dashboard typecheck` (and `build` before a release).

## Commits
- Conventional Commits (`feat(replay): ...`, `fix(dashboard): ...`, `test(support): ...`,
  `docs(kiro): ...`). One logical change per commit.
- Messages describe what changed and why; no tool or assistant attribution trailers.
