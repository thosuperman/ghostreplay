# Security of the public demo

GhostReplay is a developer tool: it records agent runs, injects faults and generates
regression tests. Running it on the open internet needs more care than a brochure site,
so this page covers every risk the deployment brief raised and how the live system handles
it. The application-level policy is in [`SECURITY.md`](../../SECURITY.md) at the repository root.

## Attack surface

| Exposed | Not exposed |
|---|---|
| `443/tcp` and `443/udp` (HTTPS, HTTP/3) to Caddy | Lab ports `8101` and `8102`, which listen on `127.0.0.1` only |
| `80/tcp`, which only redirects to HTTPS and handles certificate challenges | Caddy's admin API, on `localhost:2019` |
| `22/tcp`, open only to the admin's IPv4 address and the Lightsail browser console | SQLite files, which sit in `0700` directories outside any web root |
| | Docker. It isn't installed. |
| | Vite or any other development server. Only the static build is served. |

Two firewalls enforce the same rules:

- the Lightsail firewall, set by `provision.sh`;
- `ufw` on the host, which denies all incoming traffic by default and allows 22, 80 and 443.

Caddy serves only `ghostreplay.hayaix.tech`. Requests for the bare IP or any other host name get a 404.

## No code execution

- **The API accepts data, never code.** Request bodies are Pydantic models with fixed fields and length limits. A scenario must be one of the two registered scenarios. Agent variants, fault kinds and presets come from fixed in-code lists.
- **Generated tests are only downloaded.** A regression export returns pytest source as text for the visitor to download. The server never writes that source to disk, imports it or runs it.
- **Server-run "regression" is a scenario replay.** It runs the regression case's scenario, variant and faults through the engine. A case's reference trace is plain data that gets replayed. There's no plugin loading, no dynamic import and no shell.
- **Tools are in-memory simulations.** The refund gateway, CRM, cloud API and health checks are Python objects with no network or process access.

## No AWS access

- **No credentials on the server.** The instance has no IAM role (Lightsail instances can't have one), no `~/.aws`, no AWS CLI and no access keys.
- **No outbound network for the labs.** Each lab service runs with `IPAddressDeny=any` and `IPAddressAllow=localhost`. The kernel drops anything the process sends anywhere except loopback. That includes the instance metadata service at `169.254.169.254`, AWS APIs and the wider internet.
- **The DevOps lab's "AWS" is fake.** `ec2.terminate_instances` and the other destructive tools change an in-memory fleet. The tests check that offline replay never calls them.

## Sandboxing (systemd)

Each lab runs as its own system user (`ghostreplay-support`, `ghostreplay-devops`) with no login shell. The sandbox settings include:

- **Filesystem:** `ProtectSystem=strict`, so the operating system and the release directory are read-only, and only that lab's data directory is writable.
- **Isolation:** `ProtectHome`, `PrivateTmp` and `PrivateDevices`.
- **Privileges:** `NoNewPrivileges` and an empty capability set.
- **System calls:** `SystemCallFilter=@system-service`, minus the privileged and resource-control groups.
- **Memory:** `MemoryDenyWriteExecute`, `MemoryHigh=320M` and `MemoryMax=450M`.
- **Processes:** `TasksMax=64`.

To check the sandbox score on the server, run `systemd-analyze security ghostreplay-support`.

## Resource limits (enforced on the server)

| Limit | Value | Where |
|---|---|---|
| Request body size | 512 KiB (app), 1 MB (Caddy) | App middleware (returns 413) and Caddy `request_body` |
| Write requests and replay streams | 30 per minute per client address, per lab | App rate limiter (returns 429) |
| Engine runs at once | 2 per lab | App semaphore (returns 503) |
| Replay stream pace | 400 ms per event at most | App, server-side cap |
| Model turns per agent run | 8 (support), 10 (devops) | Agent `MAX_STEPS` |
| Faults per counterfactual | 20 | Request model |
| Stored executions | 2,000 per lab; 80 per session; deleted after 24 h | SQLite store |
| Memory | 450 MiB per lab service | systemd |
| Logs | Journal capped at 300 MB; Caddy logs roll at 20 MiB × 5 | journald and Caddy |

Each engine run takes milliseconds, so a separate wall-clock timeout isn't needed. The step limits, the stream pace cap and the run semaphore together bound how long any request can hold resources.

## Visitor isolation

- On the first request, each browser gets an anonymous random session cookie (`gr_session`): 256 bits, `HttpOnly`, `Secure`, `SameSite=Lax`, lasting 24 h.
- The database never stores the cookie itself, only a SHA-256-derived owner key.
- Every read and write goes through a store view bound to that owner key: listing, opening, replaying, mutating, diffing, exporting and running regressions. Another visitor's execution id behaves exactly like an id that doesn't exist (404).
- A crafted regression case can't overwrite someone else's execution by reusing its id. The store refuses that update and the API returns 400.
- Visitor data expires 24 hours after it is saved, and each session keeps at most 80 runs per lab.
- There are no accounts and no personal data. Executions contain only simulated customers, payments and instances.

`tests/test_public_isolation.py` covers all of the above.

## Secrets and information leaks

- The server holds no secrets. `ghostreplay.env` contains only limits and flags and is committed on purpose.
- Live AI mode is forced off in the public profile, so no model API key is needed or read.
- `/api/info` reports `storage: "sqlite"` instead of the file path.
- The interactive API docs are disabled.
- Unhandled errors return a plain `500 Internal Server Error`; tracebacks go only to the journal.
- `Server` headers are removed.
- The framework redacts secret-looking values in recorded payloads, covered by `test_security_storage.py`.
- The repository's secret scan runs in CI and in `deploy.sh`.

## HTTP security headers (Caddy)

| Header | Value |
|---|---|
| `Strict-Transport-Security` | `max-age=31536000` |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'` |
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | Camera, microphone, geolocation and payment disabled |
| `Cross-Origin-Opener-Policy` | `same-origin` |

The dashboard bundles its fonts and has no inline scripts, so the CSP needs no exceptions beyond inline styles.

## Host hardening

- SSH accepts keys only: no passwords, no keyboard-interactive login, no root login, at most 3 attempts. Key login was checked after hardening.
- `unattended-upgrades` installs Ubuntu security updates automatically.
- uv is installed from its GitHub release and checked against a pinned SHA-256. Caddy comes from its official signed apt repository.
- Python dependencies come from `uv.lock`, with hashes verified and no development packages.

## Known limits

- Rate limits and run slots are per process and kept in memory, so they reset when a lab restarts. Each lab runs a single worker, so they are exact within that lab.
- A single client address can still cycle through sessions. The per-address rate limit and the global storage cap bound what that achieves.
- Backups live on the same disk. See [BACKUP_RESTORE.md](BACKUP_RESTORE.md).
