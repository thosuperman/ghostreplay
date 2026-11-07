#!/usr/bin/env bash
# Start both lab servers and the dashboard. Ctrl-C stops everything.
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync -q
corepack pnpm install --silent

uv run support-agent-lab serve &
uv run devops-agent-lab serve &
trap 'kill 0' EXIT INT TERM

echo
echo "  Dashboard:          http://127.0.0.1:5173"
echo "  Support Agent Lab:  http://127.0.0.1:8101/docs"
echo "  DevOps Agent Lab:   http://127.0.0.1:8102/docs"
echo
corepack pnpm --dir apps/dashboard dev
