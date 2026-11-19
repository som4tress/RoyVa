#!/usr/bin/env bash
# Read-only: samples cumulative bytes read by sda, sdb, sdc and md0 on the 3090 box once a second for up to 10 minutes into a local log, in the background, and returns at once.
# Use it next to gpu-sample.sh during an episode: it shows directly whether the first-call stalls are disk reads, and (with the stripe) that both SSDs are read in parallel.
# Run:  ! bash ~/RoyVa/scripts/remote/disk-sample.sh [seconds, default 600]     Log: ~/RoyVa/runtime/episodes/newton60_e2e/disk_sample.log
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
S="${1:-600}"
OUT="$HOME/RoyVa/runtime/episodes/newton60_e2e/disk_sample.log"
( ssh somdutta@somdutta-linux.local "timeout $S bash -s" < "$D/disk-sample-remote.sh" > "$OUT" 2>&1 & )
sleep 3
echo "sampling for up to ${S}s into $OUT"; head -3 "$OUT"
