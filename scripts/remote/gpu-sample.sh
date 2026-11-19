#!/usr/bin/env bash
# Read-only: samples the 3090 once a second for up to 10 minutes (util, clocks, power, throttle flags, PCIe MB/s) into a local log, in the background, and returns at once.
# Run:  ! bash ~/RoyVa/scripts/remote/gpu-sample.sh [seconds, default 600]     Log: ~/RoyVa/runtime/episodes/newton60_e2e/gpu_sample.log
S="${1:-600}"
OUT="$HOME/RoyVa/runtime/episodes/newton60_e2e/gpu_sample.log"
( ssh somdutta@somdutta-linux.local "timeout $S nvidia-smi dmon -s pucvt -d 1 -o T" > "$OUT" 2>&1 < /dev/null & )
sleep 3
echo "sampling for up to ${S}s into $OUT"; head -4 "$OUT"
