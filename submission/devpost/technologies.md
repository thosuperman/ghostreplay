# Technologies

Versions are taken from `uv.lock`, `pnpm-lock.yaml`, `package.json`, `.python-version`,
`Dockerfile` and `.github/workflows/ci.yml` as of 2026-11-07.

## Devpost "Built with" tags

python, uv, pydantic, fastapi, uvicorn, sqlite, pytest, ruff, typescript, react, vite,
tailwindcss, pnpm, playwright, docker, render, github-actions, anthropic, kiro

## Languages

| Language | Version | Where |
|---|---|---|
| Python | 3.13 (`.python-version`, Docker, CI); `requires-python >= 3.12` | framework, both labs, CLI, servers, tests |
| TypeScript | 7.0.2 (strict mode) | dashboard and Playwright tests |
| CSS | Tailwind CSS 4.3.4 | dashboard styling |

## Python (framework and labs)

| Library / tool | Version | Role |
|---|---|---|
| uv | 0.13.7 (pinned in CI and the Dockerfile) | workspace, dependency locking, running commands |
| Pydantic | 2.14.3 | versioned execution schema (`ghostreplay/v1`), validation of traces, cases and requests |
| FastAPI | 0.162.0 | lab HTTP APIs and the gateway |
| Starlette | 1.10.0 | ASGI toolkit under FastAPI (Server-Sent Events replay stream, static files) |
| Uvicorn | 0.54.0 | ASGI server |
| SQLite | Python standard library `sqlite3` | one store per lab |
| Hatchling | build backend (unpinned) | packaging of the workspace members |
| pytest | 9.2.0 | unit, integration and generated regression tests |
| Ruff | 0.17.4 | lint and format |
| HTTPX | 0.28.1 | test client (dev only) |
| Anthropic Python SDK | 2.6.0 (optional `live` extra) | opt-in live LLM mode; default model `claude-opus-5-5` |

## Dashboard

| Library / tool | Version | Role |
|---|---|---|
| Node.js | 24 (CI and Docker build stage); README asks for 20 or newer | build tooling |
| pnpm (via corepack) | 12.18.0 | package manager (`packageManager` field) |
| React / React DOM | 19.3.1 | UI |
| Vite | 8.3.6 | dev server with proxy to both labs, production build |
| @vitejs/plugin-react | 6.2.1 | React support for Vite |
| Tailwind CSS / @tailwindcss/vite | 4.3.4 | styling |
| Playwright (@playwright/test) | 1.65.0 | end-to-end tests against the gateway or a deployment |

No component library is used; components are in `apps/dashboard/src/components`.

## Infrastructure and CI

| Tool | Version | Role |
|---|---|---|
| Docker | multi-stage build: `node:24-slim` (dashboard build), `python:3.13-slim` (runtime) | one container for both labs and the dashboard |
| Docker Compose | `compose.yaml` | local container run: read-only filesystem, non-root user, CPU and memory limits |
| Render | Blueprint `render.yaml` (Docker web service, 1 GB disk, public profile) | intended host; not deployed yet |
| GitHub Actions | `actions/checkout@v4`, `astral-sh/setup-uv@v6`, `actions/setup-node@v4`, `actions/cache@v4`, `actions/upload-artifact@v4` | CI jobs: Python, Dashboard, End-to-end (Playwright), Container |

## Kiro

| Artifact | Location |
|---|---|
| Steering documents | `.kiro/steering/` |
| Specs (requirements, design, tasks per component) | `.kiro/specs/` |
| Agent hooks | `.kiro/hooks/` |

See the "How we used Kiro" section of `description.md` for what these contain and how they
were used.

## Not used

No AWS SDK, payment SDK, database server, message broker, Kubernetes or paid services. Every
tool in the demo is an in-memory simulation, and the default mode needs no API key.
