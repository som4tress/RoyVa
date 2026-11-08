#!/usr/bin/env bash
# Restart a command whenever it exits (dev stand-in for systemd Restart=on-failure). Backoff grows if it keeps dying quickly.
# Usage: scripts/supervise.sh <name> <command...>     Stop with: pkill -f "supervise.sh <name>"  (then the child)
name=$1; shift
fails=0
while true; do
  start=$(date +%s)
  "$@"; code=$?
  ran=$(( $(date +%s) - start ))
  echo "[supervise] $name exited with $code after ${ran}s; restarting" >&2
  if [ "$ran" -ge 60 ]; then fails=0; else fails=$((fails + 1)); fi
  sleep $(( fails > 5 ? 30 : 3 ))
done
