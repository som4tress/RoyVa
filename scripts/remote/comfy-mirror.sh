#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Read-only: mirrors the ComfyUI container log (with timestamps) to THIS machine, so that when the 3090 trips, the last phase line before the stop survives (a log kept only on the box dies with it).
# Reconnects by itself after a trip or reboot and notes each disconnect with a local timestamp. Nothing is changed on the box.
# Run in the background:  ! nohup bash ~/RoyVa/scripts/remote/comfy-mirror.sh >/dev/null 2>&1 &
# Stop:                   ! kill $(cat ~/RoyVa/runtime/box/comfy-mirror.pid)
# Read the tail:          tail -40 ~/RoyVa/runtime/box/comfy-mirror.log
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$ROOT/runtime/box"; mkdir -p "$OUT"
LOG="$OUT/comfy-mirror.log"
echo $$ > "$OUT/comfy-mirror.pid"
since=$(date -u +%Y-%m-%dT%H:%M:%S)
while true; do
  echo "$(date -u +%FT%T.%NZ) [mirror] connect (since $since)" >> "$LOG"
  ssh -o ServerAliveInterval=5 -o ServerAliveCountMax=2 -o ConnectTimeout=10 ${BOX_SSH} \
    "docker logs -f --timestamps --since $since comfyui-limited 2>&1" \
    | stdbuf -oL tr '\r' '\n' | stdbuf -oL sed 's/\x1b\[[0-9;]*m//g' | stdbuf -oL cut -c1-300 >> "$LOG"
  echo "$(date -u +%FT%T.%NZ) [mirror] LOST CONNECTION (box stopped or ssh dropped)" >> "$LOG"
  since=$(date -u -d '-30 seconds' +%Y-%m-%dT%H:%M:%S)
  sleep 5
done
