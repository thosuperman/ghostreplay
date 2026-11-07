# Shared helpers for the GhostReplay Lab server scripts (sourced, not executed).
# shellcheck shell=bash disable=SC2034,SC2054
GR_ROOT=/opt/ghostreplay
GR_RELEASES=/opt/ghostreplay/releases
GR_CURRENT=/opt/ghostreplay/current
GR_DATA=/var/lib/ghostreplay
GR_BACKUPS=/var/backups/ghostreplay
GR_LABS=(support devops)
declare -A GR_PORT=([support]=8101 [devops]=8102)
GR_DOMAIN=${GR_DOMAIN:-ghostreplay.hayaix.tech}

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }
need_root() { [ "$(id -u)" = 0 ] || die "run as root (sudo)"; }

# Remove a path only if it lies strictly inside one of the deployment's own directories.
safe_rm() {
  local target
  for target in "$@"; do
    case "$target" in
      "$GR_RELEASES"/?*|"$GR_DATA"/?*|"$GR_BACKUPS"/?*|/run/ghostreplay-monitor/?*|/tmp/?*) ;;
      *) die "refusing to remove $target" ;;
    esac
    rm -rf -- "${target:?}"
  done
}

lab_healthy() {  # lab_healthy <lab> -> 0 when /api/health reports ok
  local body
  body=$(curl -fsS -m 5 "http://127.0.0.1:${GR_PORT[$1]}/api/health" 2>/dev/null) || return 1
  [[ $body == *'"status":"ok"'* ]]
}

wait_healthy() {  # wait_healthy <seconds>
  local deadline=$((SECONDS + $1)) lab ok
  while ((SECONDS < deadline)); do
    ok=1
    for lab in "${GR_LABS[@]}"; do lab_healthy "$lab" || ok=0; done
    ((ok)) && return 0
    sleep 1
  done
  return 1
}
