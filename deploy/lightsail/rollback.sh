#!/usr/bin/env bash
# Re-activate the previous release (or a named one) on the server. Data is untouched.
#   deploy/lightsail/rollback.sh [release-id]
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.sh"
gr_ssh "sudo /usr/local/sbin/gr-rollback ${1:-}"
