# GhostReplay Lab on AWS Lightsail

**Live:** <https://ghostreplay.hayaix.tech>. It was deployed on 2026-11-07 and verified end to end on the same day.

This deployment is a single dedicated instance with nothing else on it. It doesn't share infrastructure with any other application, and no other AWS resource was created or changed. The scripts are in [`deploy/lightsail/`](../../deploy/lightsail/README.md).

## Infrastructure

| Item | Value |
|---|---|
| AWS account | `9311****9234`, profile `hayaitech`, IAM user `hayai-admin` |
| Region / zone | `us-east-1` (N. Virginia) / `us-east-1a` |
| Instance | `ghostreplay-prod`, a dedicated Lightsail Linux/Unix instance |
| Bundle | `small_3_0`: **2 GB RAM, 2 vCPU, 60 GB SSD, 3 TB transfer, public IPv4 — $12.00/month**. The price was read from the Lightsail API before provisioning. |
| OS | Ubuntu 24.04.5 LTS, kernel `7.0.0-1014-aws`, with `unattended-upgrades` on |
| Static IP | `ghostreplay-prod-ip` → **34.226.55.219** |
| SSH key pair | `ghostreplay-prod-key` (ed25519). The private key stays on the admin machine at `~/.ssh/ghostreplay-prod`. |
| DNS | Route 53 zone `hayaix.tech` (`Z0868301OHT2GP0EYYDO`): `A ghostreplay.hayaix.tech → 34.226.55.219`, TTL 300 |
| TLS | Let's Encrypt (issuer `YE1`), obtained and renewed automatically by Caddy. The first certificate is valid until 2027-02-05. |
| Tags | `Project=GhostReplay`, `Environment=Production`, `Purpose=Kiroween2026`, `Owner=Hayaix`, on the instance and the key pair. Lightsail static IPs can't be tagged. |

### Firewalls

| Port | Lightsail firewall | Host `ufw` |
|---|---|---|
| 80/tcp | 0.0.0.0/0 | allow |
| 443/tcp, 443/udp | 0.0.0.0/0 | allow |
| 22/tcp | Admin IPv4 /32 plus the `lightsail-connect` alias (browser SSH) | allow |
| Everything else | closed | deny |

The SSH rule follows the admin's IP. If that IP changes, `provision.sh` resets it.

## What runs on the instance

| Component | How it runs | Listens on |
|---|---|---|
| Caddy 2.11 | apt package, `caddy.service` | `:80`, `:443` (TCP and UDP). Admin API on `localhost:2019`. |
| Support Agent Lab API | `ghostreplay-support.service`, user `ghostreplay-support`, 1 uvicorn worker | `127.0.0.1:8101` |
| DevOps Agent Lab API | `ghostreplay-devops.service`, user `ghostreplay-devops`, 1 uvicorn worker | `127.0.0.1:8102` |
| Dashboard | Static files served by Caddy from `/opt/ghostreplay/current/dashboard` | — |
| Backups | `ghostreplay-backup.timer`, daily at 03:30 UTC | — |
| Health and resource monitor | `ghostreplay-monitor.timer`, every 5 minutes | — |

The labs are two separate processes, each with its own user, data directory and SQLite file. Each still runs on its own (`uv run support-agent-lab serve`), exactly as in development. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Why systemd, not Docker Compose

- **Each lab gets its own sandbox** (user, filesystem, system calls, memory) through plain systemd directives. Compose wouldn't be any simpler.
- **The labs have no network access beyond loopback** (`IPAddressDeny=any`). That blocks instance metadata, AWS APIs and the internet outright. Doing the same with Docker networking would need extra iptables rules.
- **No container runtime** on a 2 GB instance, and no Docker socket to protect.
- **Instant rollback** by switching a symlink between releases kept on disk, with no image registry.
- **The dashboard is built on the admin machine**, so the server only installs locked Python wheels.

The repository's `Dockerfile` and `compose.yaml` still work for other hosts. See [`docs/deployment.md`](../deployment.md).

## How it was deployed

```bash
deploy/lightsail/provision.sh   # key pair, instance, static IP, firewall, host setup (idempotent)
deploy/lightsail/dns.sh         # Route 53 UPSERT of the single A record
deploy/lightsail/deploy.sh      # checks, build, upload, activate, verify
```

## Verification

These checks were run against the live system on 2026-11-07.

**Tests and builds (local, before deploying)**

| Check | Result |
|---|---|
| `uv run pytest` | 133 passed (including 11 new session-isolation tests) |
| ruff lint and format, secret scan | clean |
| Dashboard type check and production build | passed |
| Playwright locally, against the single-process gateway | 10 passed, 1 skipped (the isolation test only applies to the public profile) |

**Browser and demo checks (public site)**

| Check | Result |
|---|---|
| **Playwright against https://ghostreplay.hayaix.tech** | **11 passed**. Covers both one-click demos, the Explorer record flow, streamed offline replay, failure injection, structural diff, regression run, every route without browser errors, and per-session isolation between two browser contexts. |
| Manual browser check | The Duplicate Refund story shows the $129 refund and the duplicate $258.00 total, verdicts fail · pass · why · fail · pass · pass. The Unsafe Infrastructure story shows stale health data, the simulated `ec2.terminate_instances`, and the approval invariant (`infra.destructive_requires_approval`). No console errors. |
| Phone width (375 px) | Every route fits without horizontal page scroll |

**HTTPS and network**

| Check | Result |
|---|---|
| HTTPS | Valid Let's Encrypt certificate. `http://` returns a 308 redirect to `https://`. HSTS, CSP, `X-Frame-Options` and the other headers are present. |
| Port scan from outside | 8101, 8102, 5173 and 2019 closed. 22 open only to the admin IP. Bare-IP requests get 404. |
| Sandbox | `systemd-analyze security` rates each lab's exposure 1.1 ("OK"). A sandboxed process can't reach `169.254.169.254` or the internet (both time out). No AWS CLI or credentials on the host. |

**Limits and abuse protection**

| Check | Result |
|---|---|
| Public limits | Rate limit returns 429 after 30 writes per minute, even with a spoofed `X-Forwarded-For`. Over-limit body returns 413. Live AI is refused. "Clear all" returns 403. `/docs` and `/openapi.json` return 404. |

**Data safety and operations**

| Check | Result |
|---|---|
| Persistence across reboot | Ran a kernel update and rebooted. All services came back by themselves within about 20 s. The same session cookie saw the same 7 + 7 runs before and after. |
| Backup and restore drill | Backup at 250 runs, a new run (251), restore, then back to 250. The old database was kept in `pre-restore-*`. The DevOps lab stayed up throughout. |
| Release rollback | `rollback.sh` to the previous release and back. Visible in the CSP header difference between the two releases. |
| Automatic rollback | Activated a deliberately broken release. The health check failed, the previous release was restored automatically, and both labs were healthy again. The first attempt exposed a systemd start-limit bug, which was fixed before the rerun. |

### Resource use (2 GB instance)

| Measurement | Value |
|---|---|
| Idle memory: support / devops / Caddy | 46 / 44 / 52 MiB |
| Host memory, idle | 461 MiB used, 1,444 MiB available of 1,905 MiB. Swap: 1 GiB file, unused. |
| Peak during a 10-visitor burst (5 concurrent, both demos plus a replay each) | support 61 MiB, devops 69 MiB, at least 1,423 MiB still available |
| CPU | Idle at about 0%. One second at about 45% user while 6 visitors started at once, then idle. Load average under 0.3. |
| Disk | 4.2 GB used of 58 GB (8%). Data about 20 MB after the testing above. |
| Server time per guided demo, which records about 7 executions | Support 0.13 s, DevOps 0.24 s |
| Latency from Tokyo (about 170 ms round trip) | API GET p50 190 ms. Demo p50 0.6 s (support) and 1.0 s (devops). Replay p50 210 ms. 0 errors. |

The 2 GB bundle has a lot of headroom. The 512 MB and 1 GB bundles were not evaluated, as instructed.

## Operations

All commands run from the repository root.

| Task | Command |
|---|---|
| SSH | `deploy/lightsail/ssh.sh`, or `ssh -i ~/.ssh/ghostreplay-prod ubuntu@34.226.55.219` |
| Status overview | `deploy/lightsail/status.sh` |
| Update (deploy HEAD) | `deploy/lightsail/deploy.sh` |
| Restart the labs | `deploy/lightsail/ssh.sh sudo systemctl restart ghostreplay-support ghostreplay-devops` |
| Reload Caddy | `deploy/lightsail/ssh.sh sudo systemctl reload caddy` |
| Logs | `deploy/lightsail/ssh.sh sudo journalctl -u ghostreplay-support -f` (also `ghostreplay-devops`, `caddy`, `ghostreplay-monitor`). Access log: `/var/log/caddy/access.log`. |
| Back up now and download | `deploy/lightsail/backup.sh` |
| Restore | `deploy/lightsail/restore.sh support <backup-file>` (see [BACKUP_RESTORE.md](BACKUP_RESTORE.md)) |
| Roll back | `deploy/lightsail/rollback.sh [release-id]` |
| Stop the instance (stops compute only; Lightsail still bills a stopped instance) | `aws --profile hayaitech --region us-east-1 lightsail stop-instance --instance-name ghostreplay-prod` |
| Delete everything after the hackathon | `deploy/lightsail/backup.sh && deploy/lightsail/teardown.sh` |

`teardown.sh` asks you to type the instance name. It then deletes, in this order:

1. the `ghostreplay` A record, and only if it still points at this instance's IP;
2. the static IP;
3. the instance and its disk;
4. the key pair.

It touches nothing else in the account or the hosted zone.

More detail:

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [COST_ESTIMATE.md](COST_ESTIMATE.md)
- [DOMAIN_AND_HTTPS.md](DOMAIN_AND_HTTPS.md)
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
- [SECURITY.md](SECURITY.md)
- [BACKUP_RESTORE.md](BACKUP_RESTORE.md)
- [UPDATE_ROLLBACK.md](UPDATE_ROLLBACK.md)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
