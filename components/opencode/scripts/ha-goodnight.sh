#!/usr/bin/env bash
# Trigger the Home Assistant "Good Night" automation (automation.good_night).
# Automations are not exposed to Assist/MCP, so we use the REST trigger service.
set -euo pipefail

HA_URL="${HA_URL:-https://som4tress.duckdns.org:8123}"
TOKEN="${HA_TOKEN:-$(grep -o 'eyJ[A-Za-z0-9._-]*' "$HOME/.zshrc" | head -1)}"

curl -sS -X POST "$HA_URL/api/services/automation/trigger" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id":"automation.good_night","skip_condition":true}' >/dev/null
echo "Good Night automation triggered"
