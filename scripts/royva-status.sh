#!/usr/bin/env bash
# One-glance health of the whole stack (read-only). Exit code 1 if anything is down.
. /home/somdutta/RoyVa/scripts/env.sh
bad=0
chk() { if eval "$2" >/dev/null 2>&1; then printf '  ok    %s\n' "$1"; else printf '  DOWN  %s\n' "$1"; bad=1; fi; }
chk "main model   :8000 (evo-llamacpp-agent)" "curl -sf -m4 http://127.0.0.1:8000/health"
chk "router 9B    :8203"                    "curl -sf -m4 http://127.0.0.1:8203/health"
chk "proxy        :8100"                    "curl -s -m4 -o /dev/null http://127.0.0.1:8100/"
chk "OpenCode     :49380"                   "curl -s -m4 -o /dev/null -u opencode:\$OPENCODE_SERVER_PASSWORD http://127.0.0.1:49380/api/mcp"
chk "gateway ready :8300 (all MCP connected)" "curl -sf -m4 http://127.0.0.1:8300/healthz | grep -q '\"ready\":true'"
chk "Telegram bridge process"               "pgrep -f '[R]oyVa/bridge/bridge.mjs'"
chk "no second Telegram poller (old bridge)" "! pgrep -f '[o]pencode-telegram-vanilla|[t]elegram-vanilla/bridge'"
exit $bad
