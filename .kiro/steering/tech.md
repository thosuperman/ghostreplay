---
inclusion: always
---

# Technology stack

## Backend and framework
- Python 3.12+ (developed on 3.13), managed with **uv** workspaces.
- **Pydantic v2** for every persisted or externally supplied structure.
- **FastAPI** + uvicorn for the lab API servers.
- **SQLite** (stdlib `sqlite3`) for local persistence. No ORM.
- **pytest** for unit, integration and generated regression tests.
- **Ruff** for linting and formatting.

## Frontend
- TypeScript (strict), React, Vite, Tailwind CSS v4.
- No heavy component library: small in-repo components (`apps/dashboard/src/components`).
- pnpm for package management.

## Explicitly out of scope
Kubernetes, Kafka, Redis, Elasticsearch, microservices, cloud deployment, auth servers,
billing, multi-tenancy. Everything runs on one developer machine, offline.

## Runtime layout
| Process | Port | Command |
|---|---|---|
| Support Agent Lab API | 8101 | `uv run support-agent-lab serve` |
| DevOps Agent Lab API | 8102 | `uv run devops-agent-lab serve` |
| Dashboard (Vite) | 5173 | `pnpm --dir apps/dashboard dev` |

The dashboard proxies `/lab/support/*` and `/lab/devops/*` to the two lab servers.

## Commands
- `uv sync` — install Python workspace.
- `uv run pytest` — all Python tests (framework, apps, generated regression tests).
- `uv run ruff check .` — lint.
- `pnpm --dir apps/dashboard build` — type-check and build the dashboard.
