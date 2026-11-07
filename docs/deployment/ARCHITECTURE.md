# Production architecture

This page describes the deployed system as it actually runs. For the framework's own design, see [`docs/architecture.md`](../architecture.md).

```text
                        Internet
                           │  https://ghostreplay.hayaix.tech
                           ▼
          Route 53 A record → Lightsail static IP 34.226.55.219
                           │
      Lightsail firewall: 80/tcp, 443/tcp+udp public · 22/tcp admin only
                           │
  ┌────────────────────── ghostreplay-prod (us-east-1a, 2 GB, Ubuntu 24.04) ──────────────────────┐
  │  ufw: deny incoming except 22, 80, 443                                                          │
  │                                                                                                 │
  │  Caddy (:80 → 308 redirect, :443 TLS · Let's Encrypt · security headers · gzip/zstd)            │
  │    ├── /                 → static dashboard  /opt/ghostreplay/current/dashboard (SPA fallback)  │
  │    ├── /assets/*         → static, immutable caching                                            │
  │    ├── /lab/support/*    → strip prefix → 127.0.0.1:8101                                        │
  │    ├── /lab/devops/*     → strip prefix → 127.0.0.1:8102                                        │
  │    └── /healthz          → proxy liveness                                                       │
  │                                                                                                 │
  │  ghostreplay-support.service                 ghostreplay-devops.service                         │
  │    user ghostreplay-support                    user ghostreplay-devops                          │
  │    support-agent-lab serve (uvicorn, 1 worker) devops-agent-lab serve (uvicorn, 1 worker)       │
  │    support_agent  ─┐                           devops_agent  ─┐                                 │
  │                    └── ghostreplay framework (shared package, same locked version) ──┘          │
  │    /var/lib/ghostreplay/support/               /var/lib/ghostreplay/devops/                     │
  │      support-agent.sqlite3 (WAL)                 devops-agent.sqlite3 (WAL)                     │
  │    sandbox: loopback only, read-only FS, no capabilities, seccomp, 450 MiB                      │
  │                                                                                                 │
  │  timers: ghostreplay-backup (daily) → /var/backups/ghostreplay · ghostreplay-monitor (5 min)    │
  └─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Request flow

1. The browser loads `index.html` and the hashed assets from Caddy. No Node.js server runs in production.
2. The dashboard calls `/lab/support/api/...` or `/lab/devops/api/...` on the same origin. Those are the same relative paths the Vite dev proxy and the single-process gateway use, so the frontend has no URLs or IP addresses to configure.
3. Caddy removes the `/lab/<name>` prefix and forwards the request to that lab on loopback. Caddy sets `X-Forwarded-For` to the real client address and ignores any value the client sends. The labs use it for rate limiting.
4. The lab's `limits` middleware runs first:
   - it rejects bodies that are too large (413) and requests over the rate limit (429);
   - it issues or reads the visitor's `gr_session` cookie;
   - it scopes the lab's store to that session.
5. The endpoint runs the GhostReplay engine in-process (record, replay, counterfactual, diff, regression) against simulated tools. Each engine run takes a run slot, at most 2 per lab.
6. Executions are stored in that lab's SQLite file with an owner key, and expire 24 hours after they're saved.
7. Replay streams use Server-Sent Events. Caddy flushes them immediately (`flush_interval -1`).

## Why this shape

- **Two processes, not one gateway.** The repository's `ghostreplay serve` gateway mounts both labs in one process and is still what Docker, Render and the CI smoke test use. Production runs each lab as its own service so that:
  - each lab has its own Unix user and data directory, and can be restarted on its own;
  - a crash in one lab can't take down the other;
  - it shows that the two Skeleton Crew apps really are independent applications on one framework.
- **One worker per lab.** Rate limits, run slots and the SQLite connection live in the process. Measured load leaves a lot of headroom (see [AWS_LIGHTSAIL.md](AWS_LIGHTSAIL.md#resource-use-2-gb-instance)), and adding processes would make the per-process limits inaccurate.
- **SQLite, one file per lab.** It keeps the existing design, there are no extra services to run, and WAL mode with a 10 s busy timeout handles the write volume easily. Neither PostgreSQL nor Redis is needed.
- **Static dashboard behind Caddy.** It's built on the admin machine, served with long-lived caching for hashed assets and `no-cache` for `index.html`, so a deploy reaches visitors on their next page load.

## Releases on disk

```text
/opt/ghostreplay/
├── current -> releases/20261107T161646Z-f198ef4046    (atomic symlink)
└── releases/
    └── <UTC time>-<commit>/
        ├── .venv/                (uv sync --frozen --no-dev --no-editable, system Python 3.12)
        ├── dashboard/            (vite build, made on the admin machine)
        ├── packages/ apps/ ...   (git archive of the commit)
        └── deploy/lightsail/     (Caddyfile, units, env, scripts; installed on activation)
/etc/ghostreplay/ghostreplay.env  (public profile settings; no secrets)
/var/lib/ghostreplay/{support,devops}/   (SQLite, 0700, one owner per lab)
/var/backups/ghostreplay/{support,devops}/  (gzip backups, 0600, root)
```

Five releases are kept, so a rollback needs no rebuild. See [UPDATE_ROLLBACK.md](UPDATE_ROLLBACK.md).

## What this deployment is not

It's one inexpensive server, with no high availability:

- An instance or Availability Zone failure means downtime until the instance is restored.
- There's no load balancer, no replica and no managed database.
- Backups are on the same disk unless downloaded with `backup.sh`.

That fits a hackathon demo with simulated data. See [BACKUP_RESTORE.md](BACKUP_RESTORE.md) for the trade-off.
