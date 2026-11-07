# Backup and restore

## What is backed up

Each lab has one SQLite database, and nothing else on the server is state:

| Lab | Database | Owner |
|---|---|---|
| Support | `/var/lib/ghostreplay/support/support-agent.sqlite3` | `ghostreplay-support`, mode `0600`, directory `0700` |
| DevOps | `/var/lib/ghostreplay/devops/devops-agent.sqlite3` | `ghostreplay-devops`, mode `0600`, directory `0700` |

Both run in WAL mode with `synchronous=NORMAL` and a 10 s busy timeout. The server can be rebuilt entirely from git plus these two files.

## How backups are taken

`gr-backup` writes backups to `/var/backups/ghostreplay/<lab>/<db>-<UTC time>-<label>.sqlite3.gz`. The directory is `0700` root and each file is `0600`. For each database it:

1. Runs Python's `sqlite3` backup API **as the lab's own user**. That gives a consistent snapshot while the service keeps running, and the WAL and SHM files never change owner.
2. Runs `PRAGMA integrity_check` on the copy and counts its executions. If the check fails, the backup is rejected.
3. Compresses the copy with gzip and keeps the newest 14 per lab. Set `GR_BACKUP_KEEP` to change that.

Backups run at these times:

| When | Label |
|---|---|
| Daily at 03:30 UTC, plus up to 15 min of jitter (`ghostreplay-backup.timer`, `Persistent=true`, so a missed run happens at boot) | `daily` |
| Before every deploy and every rollback (`gr-activate`) | `pre-deploy` |
| Before every restore | `pre-restore` |
| When you run `backup.sh` | `manual` |

## Commands

```bash
deploy/lightsail/backup.sh                 # back up now and download the newest backups to ./backups/ (git-ignored)
deploy/lightsail/backup.sh --no-download   # back up on the server only
deploy/lightsail/ssh.sh sudo ls -lt /var/backups/ghostreplay/support /var/backups/ghostreplay/devops
```

Restore from a backup that is on the server:

```bash
deploy/lightsail/restore.sh support support-agent-20261108T033012Z-daily.sqlite3.gz
```

Restore from a backup on your machine:

```bash
deploy/lightsail/restore.sh devops --upload backups/<time>/devops-devops-agent-<...>.sqlite3.gz
```

`gr-restore` does the following:

1. Decompresses the backup to a temporary file and verifies it with an integrity check and an execution count.
2. Takes a `pre-restore` backup of the live database.
3. Stops that lab only, moves the live database and its WAL and SHM files into `pre-restore-<time>/` inside the lab's data directory, installs the restored file with the right owner and mode, and starts the lab.
4. Waits for `/api/health` to return `ok`.

The other lab keeps running throughout, and nothing is deleted.

## Risks and limits

- **The backups are on the same disk as the data.** They protect against bad deploys, mistakes and corruption, but not against losing the instance or its disk. For off-instance copies, run `backup.sh` (it downloads to your machine) before risky changes and before tearing down. Lightsail snapshots, at about $0.05 per GB-month, would also cover that, but they cost money and weren't approved, so they aren't set up.
- **The data is demo data.** It contains no personal data, only simulated runs that expire after 24 hours. Losing it is an inconvenience, not an incident. The compressed backups are still root-only.
- **Restoring replaces the whole database for one lab.** Runs created between the backup and the restore are only in the `pre-restore-*` copy.

## Restore drill

The restore procedure was tested on the live server during the first deployment. [AWS_LIGHTSAIL.md](AWS_LIGHTSAIL.md#verification) records the result.
