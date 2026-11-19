#!/usr/bin/env bash
# Read-only investigation of the ~21 s first-sampler load in each Wan job. Starts one small Wan test (3 clips, about 2 min on the 3090) from this machine and, at the same time, samples the 3090 box once a second for 100 s:
# disk read rate of the model stripe (md127), host CPU busy %, RAM (Cached / free), GPU utilisation, GPU memory, current PCIe generation and width. Output goes to ~/RoyVa/runtime/diag/ and a summary prints at the end.
# Run when the GPU is idle (tell the owner first):   ! bash ~/RoyVa/scripts/remote/wan-load-watch.sh
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; O="$R/runtime/diag/wanload-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$O"
ssh somdutta@somdutta-linux.local 'for i in $(seq 1 100); do echo "$(date +%s.%N) $(awk "\$3==\"md127\"{print \$6}" /proc/diskstats) $(awk "/^cpu /{print \$2+\$3+\$4+\$7+\$8, \$5+\$6}" /proc/stat) $(awk "/^Cached:/{c=\$2}/^MemFree:/{f=\$2}END{print c, f}" /proc/meminfo) $(nvidia-smi --query-gpu=utilization.gpu,memory.used,pcie.link.gen.current,pcie.link.width.current --format=csv,noheader,nounits | tr -d " ")"; sleep 1; done' > "$O/box.log" 2>"$O/box.err" &
SSH=$!; date +%s.%N > "$O/local_start"; sleep 3
( cd "$R/agents/img_video" && python3 bench/wan_probe.py > "$O/wan.log" 2>&1 ); wait $SSH
python3 - "$O" <<'PY'
import sys, re
o = sys.argv[1]; rows = [l.split() for l in open(o + "/box.log") if len(l.split()) >= 7 and l.split()[6].count(",") == 3]
wan = open(o + "/wan.log").read(); print(wan[-900:])
local0 = float(open(o + "/local_start").read()); ws = float(re.search(r"WAN_START ([\d.]+)", wan).group(1)) if "WAN_START" in wan else local0
t_start = float(rows[0][0]) + (ws - local0)          # this machine's clock and the box's clock may differ: align the first sample with the moment ssh started
print("sec_from_job_start  disk_MB/s  cpu_busy%  GPU%  GPU_MiB  PCIe  cached_GB free_GB")
prev = None
for r in rows:
    t = float(r[0]); sect = int(r[1]); busy, idle = int(r[2]), int(r[3]); cached, free = int(r[4]), int(r[5]); gpu, mem, gen, wid = r[6].split(",")
    if prev:
        dt = t - prev[0]; dsec = (sect - prev[1]) * 512 / 1e6 / dt; cpu = 100 * (busy - prev[2]) / max(1, (busy - prev[2]) + (idle - prev[3]))
        print(f"{t - t_start:8.0f}   {dsec:9.0f}  {cpu:8.0f}  {gpu:>4}  {mem:>7}  g{gen}x{wid}  {cached / 1e6:7.1f} {free / 1e6:7.1f}")
    prev = (t, sect, busy, idle)
PY
echo "files: $O"
