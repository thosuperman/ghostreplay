# Troubleshooting

All commands run from the repository root on your machine. `deploy/lightsail/ssh.sh <cmd>`
runs a command on the server, and `deploy/lightsail/ssh.sh` on its own opens a shell.

## First look

```bash
deploy/lightsail/status.sh
```

This shows:

- the active release and the releases kept;
- the state of `caddy`, both lab services and both timers;
- each lab's `/api/health` response and memory use;
- `free -m`, `df -h /`, the size of the data and backup directories;
- the last monitor lines.

## Logs

```bash
deploy/lightsail/ssh.sh sudo journalctl -u ghostreplay-support -n 100 --no-pager
deploy/lightsail/ssh.sh sudo journalctl -u ghostreplay-devops -f          # follow
deploy/lightsail/ssh.sh sudo journalctl -u caddy -n 100 --no-pager        # TLS, config
deploy/lightsail/ssh.sh sudo tail -n 50 /var/log/caddy/access.log         # requests (JSON)
deploy/lightsail/ssh.sh sudo journalctl -u ghostreplay-monitor --since -2h -o cat
deploy/lightsail/ssh.sh sudo journalctl -u ghostreplay-backup -o cat
```

## Symptoms

| Symptom | Likely cause | What to do |
|---|---|---|
| The site shows "Support Agent Lab is temporarily unavailable" | That lab's process is down or restarting | Check `status.sh` and the lab's journal. systemd restarts it within 3 s, and the monitor restarts it after two failed checks. |
| `502 Bad Gateway` on `/lab/...` | The lab isn't listening (mid-restart or crashed) | Same as above. During a deploy, a few seconds of 502 is expected. |
| `503 the lab is busy` | Both run slots are in use | Retry. If it persists, look for a stuck process in the journal. |
| `429 rate limit exceeded` | More than 30 runs or streams per minute from one address | Wait a minute. Raise `GHOSTREPLAY_RATE_LIMIT_PER_MINUTE` only if real visitors hit it. |
| The browser shows a certificate error | Certificate not issued yet, DNS wrong, or port 80/443 blocked | `dig +short ghostreplay.hayaix.tech` must return the static IP. Check `journalctl -u caddy` for ACME errors. Ports 80 and 443 must be open in both firewalls. The CAA record on `hayaix.tech` allows only `letsencrypt.org`. |
| `ssh: connect ... timed out` | Your public IP changed, and the Lightsail firewall only allows the old one | Run `deploy/lightsail/provision.sh` again; it resets the SSH rule to your current IP. Or use the Lightsail console's browser SSH, which is always allowed. |
| `deploy.sh` says "health check failed" | The new release didn't start | It has already rolled back automatically. Read the 30 journal lines it printed, fix, commit and deploy again. |
| The Explorer is empty for a visitor | Expected: each browser session only sees its own runs | Run a guided demo. Runs expire 24 h after creation. |
| Disk warning from the monitor | Logs or backups growing | `du -sh /var/lib/ghostreplay/* /var/backups/ghostreplay /var/log`; lower `GR_BACKUP_KEEP`. |
| Memory warning from the monitor | Unusual load | `status.sh` shows memory per lab. Each lab is capped at 450 MiB and restarted by systemd if killed. |

## Run a lab by hand on the server

```bash
deploy/lightsail/ssh.sh
sudo systemctl stop ghostreplay-support
sudo -u ghostreplay-support env $(grep -v '^#' /etc/ghostreplay/ghostreplay.env | xargs) \
  /opt/ghostreplay/current/.venv/bin/support-agent-lab --db /var/lib/ghostreplay/support \
  serve --host 127.0.0.1 --port 8101
# Ctrl-C, then:
sudo systemctl start ghostreplay-support
```

## Check the sandbox and the egress block

```bash
deploy/lightsail/ssh.sh sudo systemd-analyze security ghostreplay-support --no-pager | tail -1
deploy/lightsail/ssh.sh sudo systemd-run --wait --pipe -p User=ghostreplay-support \
  -p IPAddressDeny=any -p IPAddressAllow=localhost \
  curl -sS -m 3 http://169.254.169.254/latest/meta-data/   # must fail
```

## Verify the Caddy configuration

```bash
deploy/lightsail/ssh.sh sudo caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile
```

## Start over on the same instance

Every script is idempotent. `provision.sh` re-applies the host setup and the firewall, and `deploy.sh` installs a fresh release. Neither deletes data.
