#!/usr/bin/env bash
# One-glance health of the whole stack (read-only). Exit code 1 if anything is down.
. "$(dirname "$(readlink -f "$0")")/env.sh"
bad=0
chk() { if eval "$2" >/dev/null 2>&1; then printf '  ok    %s\n' "$1"; else printf '  DOWN  %s\n' "$1"; bad=1; fi; }
chk "main model   :8000 (evo-llamacpp-agent)" "curl -sf -m4 http://127.0.0.1:8000/health"
chk "router 9B    :8203"                    "curl -sf -m4 http://127.0.0.1:8203/health"
chk "proxy        :8100"                    "curl -s -m4 -o /dev/null http://127.0.0.1:8100/"
chk "OpenCode     :49380"                   "curl -s -m4 -o /dev/null -u opencode:\$OPENCODE_SERVER_PASSWORD http://127.0.0.1:49380/api/mcp"
chk "gateway ready :8300 (all MCP connected)" "curl -sf -m4 http://127.0.0.1:8300/healthz | grep -q '\"ready\":true'"
chk "Telegram bridge process"               "pgrep -f '[R]oyVa/bridge/bridge.mjs'"
chk "no second Telegram poller (old bridge)" "! pgrep -f '[o]pencode-telegram-vanilla|[t]elegram-vanilla/bridge'"
chk "MCP: ha-api + machine connected"      "curl -sf -m4 -u opencode:\$OPENCODE_SERVER_PASSWORD http://127.0.0.1:49380/api/mcp | python3 -c \"import sys,json;d=json.load(sys.stdin);d=d.get('data',d);s={x['name']:x['status']['status'] for x in d};sys.exit(0 if s.get('ha-api')=='connected' and s.get('machine')=='connected' else 1)\""
chk "sandbox available (bwrap works)"       "bwrap --ro-bind / / --unshare-net true"
chk "running build is the committed build"  "[ \"\$(git -C \"\$R\" log -1 --format=%ct -- bridge gateway/royva_gateway gateway/registry mcp)\" -le \"\$(date -d \"\$(ps -o lstart= -p \$(pgrep -f '[R]oyVa/bridge/bridge.mjs' | head -1))\" +%s)\" ]"
exit $bad
