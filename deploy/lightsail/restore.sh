#!/usr/bin/env bash
# Restore one lab's database from a backup.
#   deploy/lightsail/restore.sh <support|devops> <server-backup-file>
#   deploy/lightsail/restore.sh <support|devops> --upload <local-backup.sqlite3.gz>
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.sh"
lab=${1:?lab}; shift
case "$lab" in support|devops) ;; *) die "lab must be support or devops" ;; esac
if [ "${1:-}" = --upload ]; then
  file=${2:?local backup file}
  remote=/tmp/gr-restore-upload.sqlite3.gz
  gr_scp -q "$file" "$GR_SSH_USER@$(gr_ip):$remote"
  gr_ssh "sudo /usr/local/sbin/gr-restore $lab $remote; rm -f $remote"
else
  file=${1:?backup file (see: ssh.sh sudo ls /var/backups/ghostreplay/$lab)}
  case "$file" in /*) ;; *) file=/var/backups/ghostreplay/$lab/$file ;; esac
  gr_ssh "sudo /usr/local/sbin/gr-restore $lab '$file'"
fi
