#!/usr/bin/env bash
# Read-only: how much of each video-model file is in the box's page cache right now (fincore), plus free RAM and the container's memory.
# Use it before and after a batch to tell whether the GPU idle time at the start of each job is disk reads:  files mostly cached + idle stretches still there = not the disk.
# Run:  ! bash ~/RoyVa/scripts/remote/cache-check.sh [extra filename pattern, default none]
P="${1:-}"
ssh somdutta@somdutta-linux.local "P='$P' bash -s" <<'R'
M="$HOME/comfyui/data/models"
command -v fincore >/dev/null || { echo "fincore not installed on the box (util-linux)"; exit 1; }
echo "== page cache per model file (cached / size) =="
find "$M" -type f \( -name '*14B*' -o -name 'umt5*' -o -name '*wan*vae*' -o -name 'flux*' -o -name '*lightx2v*' ${P:+-o -name "$P"} \) 2>/dev/null | sort | while read -r f; do
  fincore -b -n -o RES,SIZE "$f" 2>/dev/null | awk -v f="$(basename "$f")" '{ if ($2>0) printf "%-62s %6.2f / %6.2f GB  %3.0f%%\n", f, $1/1073741824, $2/1073741824, 100*$1/$2 }'
done
echo "== host memory =="
free -m | awk 'NR<=2'
echo "== container =="
docker stats --no-stream --format 'mem {{.MemUsage}} ({{.MemPerc}})' comfyui-limited 2>/dev/null
R
