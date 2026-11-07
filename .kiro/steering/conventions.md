---
inclusion: fileMatch
fileMatchPattern: ["**/*.py", "**/*.ts", "**/*.tsx"]
---

# Coding conventions

## Python
- Type hints everywhere; `from __future__ import annotations` in modules with forward refs.
- Pydantic models for data crossing a boundary (storage, HTTP, trace files). Dataclasses for
  internal-only value objects.
- Errors: raise specific exceptions from `ghostreplay.core.errors`; never `except Exception:
  pass`. Replay divergence must never be swallowed silently.
- Public framework functions get a docstring stating the guarantee they provide.
- Tests live next to the package they test (`packages/*/tests`, `apps/*/tests`). Name tests
  after the guarantee: `test_replay_never_invokes_tool_handlers`.
- Ruff clean (`uv run ruff check .`). Line length 100.

## TypeScript / React
- `strict: true`; no `any` in application code (use `unknown` + narrowing).
- API types mirror the Pydantic schema in `apps/dashboard/src/api/types.ts`.
- Components are small and presentational; data fetching lives in `src/api`.
- Tailwind utility classes; colour tokens defined once in `src/index.css`.
- Status colours: success = emerald, warning = amber, failure = rose, injected = fuchsia,
  replay/recorded = cyan, accent = violet.

## Commits
Conventional Commits (`feat(replay): ...`, `fix(dashboard): ...`).
