#!/usr/bin/env bash
# Build, ship and activate a release of the committed HEAD (also the update command).
#
#   deploy/lightsail/deploy.sh             # checks, build, upload, activate, verify
#   GR_SKIP_CHECKS=1 deploy/lightsail/deploy.sh   # skip the local test run
#
# The dashboard is built here, not on the 2 GB server. The server installs the locked Python
# dependencies, backs up the databases, switches releases atomically and rolls back by
# itself if the new release fails its health checks. Data directories are never touched.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.sh"
repo=$(cd "$here/../.." && pwd)
cd "$repo"

[ -z "$(git status --porcelain)" ] || [ "${GR_ALLOW_DIRTY:-}" = 1 ] \
  || die "working tree has uncommitted changes; commit first (a release is built from HEAD)"
sha=$(git rev-parse --short=10 HEAD)
id=$(date -u +%Y%m%dT%H%M%SZ)-$sha

if [ "${GR_SKIP_CHECKS:-}" != 1 ]; then
  log "local checks: ruff, pytest, secret scan, dashboard typecheck"
  uv run ruff check . && uv run ruff format --check .
  uv run pytest -q
  uv run python scripts/secret_scan.py
  corepack pnpm --dir apps/dashboard typecheck
fi

log "building the dashboard"
corepack pnpm --dir apps/dashboard build >/dev/null
grep -rqE 'localhost|127\.0\.0\.1' apps/dashboard/dist/index.html apps/dashboard/dist/assets/*.js \
  && log "note: the bundle mentions localhost (developer hints only shown on localhost)"

stage=$(mktemp -d "${TMPDIR:-/tmp}/gr-release.XXXXXX")
trap 'case "$stage" in */gr-release.*) rm -rf -- "${stage:?}" ;; esac' EXIT
log "packaging release $id"
git archive --format=tar HEAD | tar -x -C "$stage"
mkdir -p "$stage/dashboard"
cp -R apps/dashboard/dist/. "$stage/dashboard/"
tarball=$stage/../ghostreplay-$id.tar.gz
# No macOS extended attributes or AppleDouble files in the release.
COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata -czf "$tarball" -C "$stage" . 2>/dev/null \
  || tar -czf "$tarball" -C "$stage" .
log "release size $(du -h "$tarball" | cut -f1)"

ip=$(gr_ip)
log "uploading to $ip"
gr_scp -q "$tarball" "$GR_SSH_USER@$ip:/tmp/ghostreplay-$id.tar.gz"
case "$tarball" in */ghostreplay-*.tar.gz) rm -f -- "${tarball:?}" ;; esac
log "installing and activating on the server"
gr_ssh "sudo /usr/local/sbin/gr-install-release /tmp/ghostreplay-$id.tar.gz $id"

log "verifying https://$GR_DOMAIN"
for path in /healthz /lab/support/api/health /lab/devops/api/health; do
  printf '  %-26s ' "$path"
  curl -fsS -m 15 "https://$GR_DOMAIN$path" || echo "(not reachable yet)"
  echo
done
log "deployed $id"
