#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Proves the server-side guard is really active (ComfyUI would otherwise let graphs through silently). Sends ONE deliberately invalid graph (a node class that does not exist, so ComfyUI rejects it and never runs any GPU work)
# carrying a 2,000-character string, then reads the guard's log on the box: the last line must say was 2000, sent <= 500. Run:  ! bash ~/RoyVa/scripts/remote/prompt-guard-verify.sh
B=${BOX_SSH}; U=http://${BOX_HOST}:8188
python3 - "$U" <<'PY'
import json, sys, urllib.request, urllib.error
body = json.dumps({"prompt": {"1": {"class_type": "PromptGuardProbeNotARealNode", "inputs": {"text": "probe " * 334}}}}).encode()
try: urllib.request.urlopen(urllib.request.Request(sys.argv[1] + "/prompt", data=body, headers={"Content-Type": "application/json"}), timeout=15)
except urllib.error.HTTPError as e: print("ComfyUI rejected the probe graph (expected), HTTP", e.code)
PY
echo "--- last lines of the guard's log on the box:"
ssh "$B" 'tail -n 3 ~/comfyui/data/prompt_guard.jsonl 2>/dev/null || echo "NO LOG: the guard is NOT active"'
echo "--- container log line:"; ssh "$B" "docker logs comfyui-limited 2>&1 | grep -E 'prompt_length_guard' | tail -n 3"
