# Lightsail deployment scripts

These scripts deploy GhostReplay Lab to one dedicated AWS Lightsail instance behind Caddy. The production deployment is <https://ghostreplay.hayaix.tech>. Full documentation is in [`docs/deployment/`](../../docs/deployment/AWS_LIGHTSAIL.md).

## Run on your machine

You need the AWS CLI with the `hayaitech` profile, `ssh`, `uv` and `corepack pnpm`.

| Script | What it does |
|---|---|
| `provision.sh` | Creates the SSH key pair, the 2 GB instance, the static IP and the firewall rules, then runs `server-setup.sh` on the instance. It only creates what's missing, so it's safe to re-run. Re-run it if your IP changes, to update the SSH rule. |
| `dns.sh` | Route 53 `UPSERT` of the single `A ghostreplay.hayaix.tech` record |
| `deploy.sh` | Checks, builds the dashboard, packages `HEAD`, uploads it, installs and activates it, then verifies. This is also the update command. |
| `rollback.sh [id]` | Re-activates the previous (or a named) release |
| `backup.sh [--no-download]` | Backs up on the server now and downloads the result to `./backups/` |
| `restore.sh <lab> <file>` / `restore.sh <lab> --upload <file>` | Restores one lab's database |
| `status.sh` | Shows services, health, memory, disk and recent monitor lines |
| `ssh.sh [cmd]` | Opens a shell, or runs a command, on the instance |
| `teardown.sh` | Deletes the A record, static IP, instance and key pair (asks for confirmation) |
| `config.sh` | Shared names and settings. Every value can be overridden from the environment. |

## Installed on the server

| File | Installed as | Purpose |
|---|---|---|
| `server-setup.sh` | run once by `provision.sh` | Packages, Caddy, uv (checksum-pinned), swap, users, directories, journald limits, SSH hardening, `ufw` |
| `Caddyfile` | `/etc/caddy/Caddyfile` | TLS, headers, static dashboard, `/lab/*` reverse proxy |
| `ghostreplay.env` | `/etc/ghostreplay/ghostreplay.env` | Public-profile settings (no secrets) |
| `systemd/*.service`, `*.timer` | `/etc/systemd/system/` | Two sandboxed lab services, daily backup, 5-minute monitor |
| `bin/gr-*` | `/usr/local/sbin/` | `gr-install-release`, `gr-activate`, `gr-rollback`, `gr-backup`, `gr-restore`, `gr-monitor`, `gr-status` |

Each deploy installs that release's copies of these files, so the server always runs the configuration that's in git.
