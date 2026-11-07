# Deployment

GhostReplay Lab ships as **one container** that serves both lab APIs and the dashboard:

| Path | What |
|---|---|
| `/` | dashboard (static build) |
| `/lab/support/api/*` | Support Agent Lab API |
| `/lab/devops/api/*` | DevOps Agent Lab API |
| `/healthz` | liveness (process up) |
| `/api/health` | readiness (both SQLite stores answer) |

The two labs remain independent applications (each also runs alone with
`uv run support-agent-lab serve` / `uv run devops-agent-lab serve`). The gateway
(`ghostreplay serve`) discovers them through the `ghostreplay.labs` entry point and mounts
them side by side.

## Run locally with Docker

```bash
docker compose up --build
```

Open http://127.0.0.1:8100. Data persists in the `ghostreplay-data` volume. The Compose
service runs read-only, as an unprivileged user, with CPU and memory limits.

Without Docker:

```bash
corepack pnpm install && corepack pnpm --dir apps/dashboard build
```

```bash
uv run ghostreplay serve --port 8100
```

## Public deployment profile

Set `GHOSTREPLAY_PUBLIC=1` on any internet-facing deployment. It enables:

| Control | Default | Variable |
|---|---|---|
| Rate limit on POST/DELETE and replay streams, per client | 30/min | `GHOSTREPLAY_RATE_LIMIT_PER_MINUTE` |
| Concurrent engine runs (others get HTTP 503) | 2 | `GHOSTREPLAY_MAX_CONCURRENT_RUNS` |
| Request body cap | 512 KiB | `GHOSTREPLAY_MAX_BODY_BYTES` |
| Stored executions per lab (oldest pruned) | 400 | `GHOSTREPLAY_MAX_EXECUTIONS` |
| Clearing all executions | disabled | — |
| Live LLM mode | disabled, even if `GHOSTREPLAY_LIVE=1` | — |
| Client address from `X-Forwarded-For` | off | `GHOSTREPLAY_TRUST_PROXY=1` behind a proxy |

What the public API can do is bounded by design: every tool is an allowlisted in-memory
simulation, request bodies are Pydantic-validated data, nothing is evaluated or executed
from requests or trace files, and no endpoint reaches a real service. A run is a few
milliseconds of CPU; the limits above bound abuse.

## Render (recommended host)

[`render.yaml`](../render.yaml) is a Render Blueprint for one Docker web service with a 1 GB
persistent disk at `/data` and the public profile switched on.

1. Push the repository to GitHub.
2. In Render: **New → Blueprint**, select the repository, confirm.
3. Wait for the health check (`/api/health`) to pass, then open the service URL.
4. Click **Try the Duplicate Refund Demo** and **Try the Unsafe Infrastructure Demo**.

A persistent disk needs a paid instance type. On a free instance, drop the `disk` block:
the app still works, but stored executions are lost on restart. That is acceptable for a
demo, because both guided demos record fresh executions on demand.

Any host that runs a Dockerfile works the same way (Fly.io, Railway, Google Cloud Run,
a VM): expose `$PORT`, mount a volume at `/data`, and set `GHOSTREPLAY_PUBLIC=1`.

## Verifying a deployment

```bash
curl -fsS https://<your-host>/api/health
```

```bash
curl -fsS -X POST https://<your-host>/lab/support/api/demo/prepare \
  -H 'content-type: application/json' -d '{"scenario":"duplicate-refund"}' | python3 -c \
  'import json,sys; print("demo ok:", json.load(sys.stdin)["ok"])'
```

The end-to-end browser tests can also run against a deployment:

```bash
E2E_BASE_URL=https://<your-host> corepack pnpm --dir apps/dashboard e2e
```
