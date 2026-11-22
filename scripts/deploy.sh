#!/usr/bin/env bash
# The safe way to load changes: run every check first, and only if they pass restart the stack in dependency order, then wait until it is healthy.
# Run as yourself in a normal terminal (Claude cannot run systemctl).
set -e
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$R/scripts/check.sh"
echo "== rendering config/opencode.json from the template (a new MCP server only exists after this)"; bash "$R/scripts/render-config.sh" || exit 1
echo "== restarting (opencode -> gateway -> bridge)"
systemctl --user restart royva-opencode
sleep 3
systemctl --user restart royva-gateway
systemctl --user restart royva-bridge
echo "== waiting for health (up to 120s)"
for i in $(seq 1 24); do
  sleep 5
  if "$R/scripts/royva-status.sh" >/dev/null 2>&1; then "$R/scripts/royva-status.sh"; echo "deploy ok"; exit 0; fi
done
"$R/scripts/royva-status.sh" || true
echo "deploy finished but the stack is not healthy: see the DOWN lines above" >&2
exit 1
