#!/usr/bin/env bash
# Open an SSH session (or run a command) on the instance.
#   deploy/lightsail/ssh.sh                      # interactive shell
#   deploy/lightsail/ssh.sh journalctl -u ghostreplay-support -f
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.sh"
if [ $# -eq 0 ]; then gr_ssh; else gr_ssh -t "$@"; fi
