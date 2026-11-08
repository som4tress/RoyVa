#!/usr/bin/env bash
# Listener for messages the owner sends to Claude over Telegram. Run under Claude Code's Monitor.
# - replays anything not yet shown (offset file), then follows new lines, so a restart/expiry never loses a message
# - writes a heartbeat so the bridge can tell the user whether Claude is listening right now
D=/home/somdutta/RoyVa/runtime/claude
mkdir -p "$D"; touch "$D/inbox.jsonl"
OFF="$D/inbox.offset"
[ -f "$OFF" ] || stat -c %s "$D/inbox.jsonl" > "$OFF"
( while true; do date +%s > "$D/watch.alive"; sleep 15; done ) &
HB=$!
trap 'kill $HB 2>/dev/null; rm -f "$D/watch.alive"' EXIT
seen=$(cat "$OFF")
tail -c +$((seen + 1)) -f "$D/inbox.jsonl" | while IFS= read -r line; do
  echo "$line"
  stat -c %s "$D/inbox.jsonl" > "$OFF"
done
