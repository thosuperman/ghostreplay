#!/usr/bin/env bash
# Take an on-server backup now and copy the newest backups to ./backups/<timestamp>/.
#   deploy/lightsail/backup.sh [--no-download]
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.sh"
gr_ssh "sudo /usr/local/sbin/gr-backup manual"
[ "${1:-}" = --no-download ] && exit 0
dest=$here/../../backups/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$dest"; chmod 700 "$dest"
for lab in support devops; do
  latest=$(gr_ssh "sudo ls -1t /var/backups/ghostreplay/$lab/ | head -n1")
  gr_ssh "sudo cat /var/backups/ghostreplay/$lab/$latest" > "$dest/$lab-$latest"
  chmod 600 "$dest/$lab-$latest"
done
log "downloaded to $(cd "$dest" && pwd) (git-ignored)"
