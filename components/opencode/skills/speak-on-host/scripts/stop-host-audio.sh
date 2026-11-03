#!/usr/bin/env bash
# Stop (or inspect) radio/stream playback started on the master host.
#   stop-host-audio.sh            # stop streams
#   stop-host-audio.sh --status   # show what is playing
set -euo pipefail
HOST="${SAY_HOST:-shivangsh@somdutta-linux.local}"
REMOTE=/run/user/1001

if [ "${1:-}" = "--status" ]; then ACTION=status; else ACTION=stop; fi

if [ -n "${SSHPASS:-}" ]; then SSH=(sshpass -e ssh); else SSH=(ssh); fi

"${SSH[@]}" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 "$HOST" \
  "export XDG_RUNTIME_DIR=$REMOTE; ACTION=$ACTION bash -s" <<'REMOTE_EOF'
if [ "$ACTION" = status ]; then
  echo "--- players"
  pgrep -af 'vlc|ffplay|mpv' | grep -v -E 'bash -s|pgrep' || echo "none"
  echo "--- active streams"
  pactl list sink-inputs 2>/dev/null | grep -E 'application.name|media.name' || echo "none"
  exit 0
fi
pkill -f 'somafm|ice1|ice2' 2>/dev/null || true
pkill -f 'vlc.*stream' 2>/dev/null || true
sleep 1
if pgrep -af 'vlc|ffplay|mpv' | grep -v -E 'bash -s|pgrep' >/dev/null; then
  echo "still running - kill manually as the owning user"
  pgrep -af 'vlc|ffplay|mpv' | grep -v -E 'bash -s|pgrep'
else
  echo "stopped"
fi
REMOTE_EOF