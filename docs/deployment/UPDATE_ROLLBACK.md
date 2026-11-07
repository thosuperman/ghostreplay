# Updating and rolling back

## Update (every deploy after the first)

```bash
git commit ...                      # a release is always built from the committed HEAD
deploy/lightsail/deploy.sh
```

`deploy.sh` does the following:

1. Refuses to run if the working tree has uncommitted changes (override with `GR_ALLOW_DIRTY=1`).
2. Runs the local checks: ruff lint and format, the full pytest suite, the secret scan and the dashboard type check. `GR_SKIP_CHECKS=1` skips them.
3. Builds the dashboard on your machine, so the 2 GB server never compiles frontend code.
4. Packages `git archive HEAD` plus `dashboard/` into one tarball, named `<UTC timestamp>-<commit>` (for example `20261108T101500Z-0182e6d1a2`).
5. Uploads it and runs `gr-install-release` on the server, which:
   - unpacks it into `/opt/ghostreplay/releases/<id>`;
   - runs `uv sync --frozen --no-dev --no-editable --compile-bytecode` against the release's `uv.lock`, using the system Python 3.12;
   - checks that both lab entry points exist.
6. `gr-activate` then:
   - backs up both databases with the label `pre-deploy`;
   - checks the release's Caddyfile with `caddy validate`;
   - installs the release's Caddyfile, systemd units, `ghostreplay.env` and `gr-*` scripts;
   - switches `/opt/ghostreplay/current` to the new release with an atomic symlink rename;
   - restarts both lab services and reloads Caddy, which doesn't drop connections;
   - waits up to 45 s for both `/api/health` endpoints to return `ok`;
   - if they don't, prints the last 30 log lines, switches back to the previous release, restarts it and exits with an error.
7. Calls `/healthz`, `/lab/support/api/health` and `/lab/devops/api/health` on the public URL.

The data directories `/var/lib/ghostreplay/*` are never touched by a deploy. The five most recent releases are kept, plus the active one, so rolling back needs no rebuild.

Expect a few seconds of 502 responses while the two lab processes restart. Caddy keeps serving the dashboard throughout.

## Roll back

```bash
deploy/lightsail/rollback.sh                       # back to the previous release
deploy/lightsail/rollback.sh 20261108T101500Z-0182e6d1a2   # or a specific one
deploy/lightsail/ssh.sh ls -1t /opt/ghostreplay/releases   # list releases
```

A rollback re-runs `gr-activate` on the older release. It reinstalls that release's own config, switches the symlink, restarts and runs the health checks. It doesn't roll back data. The SQLite schema change in this version is additive (two nullable columns), so older releases can read the migrated databases. To restore data as well, see [BACKUP_RESTORE.md](BACKUP_RESTORE.md).

## Restart without deploying

```bash
deploy/lightsail/ssh.sh sudo systemctl restart ghostreplay-support ghostreplay-devops
deploy/lightsail/ssh.sh sudo systemctl reload caddy
```

## Change a limit

Edit [`deploy/lightsail/ghostreplay.env`](../../deploy/lightsail/ghostreplay.env), commit and deploy. A deploy is the only supported way to change the server's configuration, so what's in git always matches what's running.

## Operating system updates

`unattended-upgrades` installs security updates every day. For everything else:

```bash
deploy/lightsail/ssh.sh 'sudo apt-get update && sudo apt-get -y upgrade'
deploy/lightsail/ssh.sh 'test -f /var/run/reboot-required && sudo reboot'
```

All services start automatically after a reboot. That was tested during the first deployment; see [AWS_LIGHTSAIL.md](AWS_LIGHTSAIL.md).
