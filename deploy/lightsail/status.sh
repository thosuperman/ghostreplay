#!/usr/bin/env bash
# Show services, health, memory, disk, data size and the last monitor lines.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.sh"
gr_ssh "sudo /usr/local/sbin/gr-status"
