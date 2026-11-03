#!/usr/bin/env bash
# Speak a line on the master host's speakers (default: Shivangsh's box).
#
#   say-on-host.sh "Hi Shivangsh"
#   say-on-host.sh "text" [sink-name]
#   say-on-host.sh --dry-run "text"
#
# Auth: prefers SSH key. Falls back to $SSHPASS if set (sshpass -e).
# Never embeds a password in this file.
set -euo pipefail

HOST="${SAY_HOST:-shivangsh@somdutta-linux.local}"
SINK="${SAY_SINK:-alsa_output.pci-0000_00_1b.0.analog-stereo}"
REMOTE=/run/user/1001

DRY=0
if [ "${1:-}" = "--dry-run" ]; then DRY=1; shift; fi
TEXT="${1:-}"; [ -n "${2:-}" ] && SINK="$2"
[ -z "$TEXT" ] && { echo "usage: $0 [--dry-run] \"text\" [sink]" >&2; exit 2; }

B64=$(printf '%s' "$TEXT" | base64 -w0)
REMOTE_CMD=$(cat <<EOF
set -e
export XDG_RUNTIME_DIR=$REMOTE
T=\$(mktemp /tmp/tts.XXXXXX.txt); W=\$(mktemp /tmp/tts.XXXXXX.wav)
trap 'rm -f "\$T" "\$W"' EXIT
# A muted sink or 0% volume makes paplay "succeed" into total silence.
if pactl get-sink-mute $SINK 2>/dev/null | grep -q yes; then
  pactl set-sink-mute $SINK 0; echo "note: sink was MUTED -> unmuted"
fi
if pactl get-sink-volume $SINK 2>/dev/null | head -1 | grep -q '/   0%'; then
  pactl set-sink-volume $SINK 70%; echo "note: sink volume was 0% -> set 70%"
fi
printf '%s' '$B64' | base64 -d > "\$T"
espeak-ng -v en-us -s 150 -f "\$T" -w "\$W"
pactl list sinks short | grep -q "$SINK.*RUNNING" && echo "sink: already RUNNING" || true
paplay --device=$SINK "\$W"
echo "spoke: $(printf '%s' "$TEXT" | head -c 60)"
EOF
)

if [ "$DRY" = 1 ]; then printf '%s\n' "$REMOTE_CMD"; exit 0; fi

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 -o BatchMode=no)
if [ -n "${SSHPASS:-}" ]; then
  sshpass -e ssh "${SSH_OPTS[@]}" "$HOST" "$REMOTE_CMD"
else
  ssh "${SSH_OPTS[@]}" "$HOST" "$REMOTE_CMD"
fi
