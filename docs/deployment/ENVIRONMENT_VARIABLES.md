# Environment variables

The production values live in [`deploy/lightsail/ghostreplay.env`](../../deploy/lightsail/ghostreplay.env).
Each release installs that file as `/etc/ghostreplay/ghostreplay.env`, and both lab services load it.
It holds no secrets, so it is committed. Production needs no API keys or AWS credentials.

## Variables set in production

| Variable | Production value | Effect |
|---|---|---|
| `GHOSTREPLAY_PUBLIC` | `1` | Turns on the hardened public profile. Everything below it in this table only applies when this is set. |
| `GHOSTREPLAY_TRUST_PROXY` | `1` | Rate limits use the client address from `X-Forwarded-For`. Caddy sets that header and ignores any value the client sends. |
| `GHOSTREPLAY_CORS_ORIGINS` | `https://ghostreplay.hayaix.tech` | The only origin allowed by CORS. The dashboard is served from the same origin, so it doesn't need CORS at all. |
| `GHOSTREPLAY_RATE_LIMIT_PER_MINUTE` | `30` | Maximum write requests and replay streams per client address per minute, per lab. Over the limit returns HTTP 429. |
| `GHOSTREPLAY_MAX_CONCURRENT_RUNS` | `2` | Maximum engine runs at once per lab. Over the limit returns HTTP 503 after 5 s. |
| `GHOSTREPLAY_MAX_BODY_BYTES` | `524288` | Request body cap (512 KiB). Caddy also caps bodies at 1 MB. |
| `GHOSTREPLAY_MAX_EXECUTIONS` | `2000` | Maximum stored executions per lab across all visitors. The oldest are deleted first. |
| `GHOSTREPLAY_MAX_EXECUTIONS_PER_SESSION` | `80` | Maximum stored executions per visitor session per lab. |
| `GHOSTREPLAY_SESSION_TTL_HOURS` | `24` | A visitor's executions are deleted this long after they were saved. The session cookie lasts the same time. |
| `GHOSTREPLAY_MAX_STREAM_DELAY_MS` | `400` | Upper limit on the replay animation's delay per event, so one stream cannot hold a run slot for long. |
| `PYTHONUNBUFFERED` / `PYTHONDONTWRITEBYTECODE` | `1` | Logs reach the systemd journal immediately. Python doesn't try to write bytecode into the read-only release; bytecode is compiled at install time instead. |

## Fixed by the public profile

These can't be changed by environment variables while `GHOSTREPLAY_PUBLIC=1`:

- Live AI mode is off. `GHOSTREPLAY_LIVE` and API keys are ignored, and the server holds no keys.
- `DELETE /api/executions` (clear all) returns 403.
- `/docs`, `/redoc` and `/openapi.json` are not served.
- Session cookies are `Secure`, `HttpOnly`, `SameSite=Lax` and `Path=/`. `GHOSTREPLAY_INSECURE_COOKIES=1` drops `Secure`; use it only for plain-HTTP testing.
- Session isolation is on. Setting `GHOSTREPLAY_SESSION_ISOLATION=0` makes all visitors share one store again.

## Set by the systemd units, not the environment file

| Setting | Support lab | DevOps lab |
|---|---|---|
| Listen address | `127.0.0.1:8101` | `127.0.0.1:8102` |
| Data directory (`--db`) | `/var/lib/ghostreplay/support` | `/var/lib/ghostreplay/devops` |
| Unix user | `ghostreplay-support` | `ghostreplay-devops` |
| Memory | high 320 MiB, max 450 MiB | same |

## Deployment scripts (on your machine)

[`deploy/lightsail/config.sh`](../../deploy/lightsail/config.sh) reads these variables. Each has a default that matches the live deployment.

| Variable | Default |
|---|---|
| `AWS_PROFILE` | `hayaitech` |
| `AWS_REGION` | `us-east-1` |
| `GR_INSTANCE` / `GR_STATIC_IP` / `GR_KEY_PAIR` | `ghostreplay-prod` / `ghostreplay-prod-ip` / `ghostreplay-prod-key` |
| `GR_BUNDLE` / `GR_BLUEPRINT` | `small_3_0` / `ubuntu_24_04` |
| `GR_DOMAIN` / `GR_HOSTED_ZONE_ID` | `ghostreplay.hayaix.tech` / `Z0868301OHT2GP0EYYDO` |
| `GR_SSH_KEY` | `~/.ssh/ghostreplay-prod` |
| `GR_ADMIN_CIDR` | This machine's public IPv4 address as `/32`, used for the SSH firewall rule |
| `GR_SKIP_CHECKS=1` | Makes `deploy.sh` skip the local test run |
| `GR_ALLOW_DIRTY=1` | Lets `deploy.sh` run with uncommitted changes. The release is still built from `HEAD`. |

See also [`.env.example`](../../.env.example) for local development, including the optional live AI variables.
