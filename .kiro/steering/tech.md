---
inclusion: always
---

# Technology stack

## Python (framework and labs)
- Python 3.12+ (`requires-python >=3.12`; the container uses 3.13), managed as a **uv
  workspace** (`packages/ghostreplay`, `apps/support-agent`, `apps/devops-agent`).
- **Pydantic v2** for every persisted or externally supplied structure (traces, cases, HTTP
  bodies).
- **FastAPI** + uvicorn for the lab APIs and the one-port gateway.
- **SQLite** via stdlib `sqlite3` (WAL mode for file stores). No ORM.
- **pytest** (`--import-mode=importlib`) for unit, integration and generated regression tests.
- **Ruff** for lint and format, line length 100, target `py312`.
- Optional extra `live` (`uv sync --extra live`) installs the `anthropic` SDK for live AI mode.
  Nothing else in the repository talks to a real external service.

## Dashboard
- TypeScript (strict, `noUncheckedIndexedAccess`), React 19, Vite, Tailwind CSS v4.
- Small in-repo components (`apps/dashboard/src/components`), no component library.
- pnpm via `corepack` (`packageManager` is pinned in the root `package.json`).

## Delivery
- Production: https://ghostreplay.hayaix.tech on one AWS Lightsail instance (2 GB,
  `us-east-1`): Caddy (TLS, static dashboard) in front of two sandboxed systemd services,
  one per lab, each with its own SQLite file. Scripts in `deploy/lightsail/`
  (`deploy.sh` ships `HEAD`, activates atomically and rolls back automatically on failed
  health checks). See #[[file:docs/deployment/AWS_LIGHTSAIL.md]].
- One container image (`Dockerfile`): dashboard build stage + Python runtime running
  `ghostreplay serve`. `compose.yaml` for local runs, `render.yaml` Blueprint for other hosts.
- CI: `.github/workflows/ci.yml` — Ruff, pytest, both CLI demos (non-zero exit when a step
  misses its expected verdict), committed + freshly generated regression cases, dashboard
  typecheck/build, Playwright e2e against the gateway, Docker build + smoke test.

## Not used (keep it that way)
Kubernetes, Kafka, Redis, Elasticsearch, microservices, auth servers, billing, multi-tenancy,
cloud SDKs (boto3, payment SDKs). The hosted demo is a single container with a SQLite volume.

## Runtime layout
| Process | Port | Command |
|---|---|---|
| Support Agent Lab API | 8101 | `uv run support-agent-lab serve` |
| DevOps Agent Lab API | 8102 | `uv run devops-agent-lab serve` |
| Dashboard (Vite dev) | 5173 | `corepack pnpm --dir apps/dashboard dev` |
| Gateway (both labs + built dashboard) | 8100 | `uv run ghostreplay serve --port 8100` |

The Vite dev server proxies `/lab/support/*` → 8101 and `/lab/devops/*` → 8102. The gateway
mounts the same paths itself, so the dashboard build works unchanged behind it.

## Commands
- `uv sync` — install the Python workspace (`./scripts/dev.sh` starts everything).
- `uv run pytest -q` — all Python tests (framework, both apps, regression cases, deployment,
  examples, secret scanner).
- `uv run pytest packages/ghostreplay/tests -q -x` — framework guarantees only.
- `uv run pytest apps tests/regression -q -x` — scenario tests + committed regression cases.
- `uv run ghostreplay test tests/regression --junit reports/junit.xml --json reports/report.json`
- `uv run support-agent-lab demo` / `uv run devops-agent-lab demo` — full story; exit 1 if a
  step does not produce its expected verdict.
- `uv run ruff check . && uv run ruff format --check .`
- `corepack pnpm --dir apps/dashboard typecheck` / `... build`
- `uv run python scripts/secret_scan.py` — repository secret scan (exit 1 on findings).

## Environment variables
Live mode: `GHOSTREPLAY_LIVE`, `GHOSTREPLAY_LIVE_PROVIDER`, `GHOSTREPLAY_LIVE_MODEL`,
`GHOSTREPLAY_LIVE_EFFORT`, `GHOSTREPLAY_LIVE_MAX_CALLS`. Serving: `GHOSTREPLAY_DB_DIR`,
`GHOSTREPLAY_DASHBOARD_DIR`, `GHOSTREPLAY_CORS_ORIGINS`. Public profile: `GHOSTREPLAY_PUBLIC`,
`GHOSTREPLAY_TRUST_PROXY`, `GHOSTREPLAY_RATE_LIMIT_PER_MINUTE`, `GHOSTREPLAY_MAX_CONCURRENT_RUNS`,
`GHOSTREPLAY_MAX_EXECUTIONS`, `GHOSTREPLAY_MAX_BODY_BYTES`, `GHOSTREPLAY_SESSION_ISOLATION`,
`GHOSTREPLAY_SESSION_TTL_HOURS`, `GHOSTREPLAY_MAX_EXECUTIONS_PER_SESSION`,
`GHOSTREPLAY_MAX_STREAM_DELAY_MS`. Reference: #[[file:.env.example]] and
#[[file:docs/deployment/ENVIRONMENT_VARIABLES.md]].
