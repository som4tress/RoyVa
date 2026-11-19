#!/usr/bin/env bash
# READ-ONLY: samples GPU / CPU / memory load on the 3090 box once a second for 60 seconds. Changes nothing, starts nothing.
# Run it while the thing you care about (the class) is going on.
N="${1:-60}"
echo "== GPU, one line per second: util% = compute, mem-util% = memory bandwidth, enc/dec = video encode/decode engines"
nvidia-smi --query-gpu=timestamp,utilization.gpu,utilization.memory,utilization.encoder,utilization.decoder,memory.used,power.draw,clocks.sm,temperature.gpu --format=csv,noheader -l 1 &
P=$!
sleep "$N"; kill $P 2>/dev/null
echo "== GPU processes now"
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
nvidia-smi pmon -c 1 2>/dev/null | head -15
echo "== CPU / memory (vmstat, 10 samples)"
vmstat 1 10
echo "== busiest processes by CPU"
ps -eo pid,pcpu,pmem,comm --sort=-pcpu | head -8
echo "== load average and cores"
uptime; nproc
