#!/usr/bin/env bash
# READ-ONLY, runs on the 3090 box: what changed recently (kernel, driver, packages, containers, models, cron) and what else uses the box. Changes nothing, starts no GPU work.
echo "== kernel + NVIDIA driver per boot (oldest first)"
for b in -4 -3 -2 -1 0; do
  echo "boot $b: $(journalctl -k -b $b --no-pager 2>/dev/null | grep -m1 -o 'Linux version [^ ]*') | $(journalctl -k -b $b --no-pager 2>/dev/null | grep -m1 -o 'NVIDIA UNIX x86_64 Kernel Module  [0-9.]*' | tr -s ' ')"
done
echo; echo "== package changes since Nov 10 (dpkg)"
grep -h -E "^2026-11-(1[0-9]|0[89])" /var/log/dpkg.log* 2>/dev/null | grep -E " (install|upgrade|remove) " | grep -i -E "nvidia|linux-(image|modules|headers)|docker|containerd|systemd |libc6|firmware|intel-microcode|amd64-microcode" | cut -c1-170 | tail -25
echo; echo "== apt history, last entries"; grep -E "^(Start-Date|Commandline|Upgrade)" /var/log/apt/history.log 2>/dev/null | tail -9 | cut -c1-300
echo; echo "== Docker images / containers"
docker images --format '{{.Repository}}:{{.Tag}}  created {{.CreatedSince}}' 2>&1 | head -8
docker ps -a --format '{{.Names}}  {{.Image}}  {{.Status}}' 2>&1 | head -8
echo; echo "== newest model files and custom nodes"
ls -lt --time-style=long-iso ~/comfyui/data/models/*/ 2>/dev/null | grep -v '^total' | head -8 | cut -c1-150
ls -lt --time-style=long-iso ~/comfyui/data/custom_nodes 2>/dev/null | head -5
echo; echo "== cron / timers"
crontab -l 2>/dev/null | grep -v '^#' | head; systemctl list-timers --no-pager 2>/dev/null | head -8 | cut -c1-150
echo; echo "== who is on the box, and other GPU users"
w -h | cut -c1-120; nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
echo; echo "== load now"; uptime; ps -eo pcpu,pmem,comm --sort=-pcpu | head -6
echo; echo "== sensors / RAPL (if present)"
(sensors 2>/dev/null | grep -i -E "package|core 0|fan|tctl|temp1" | head -6) || true
ls /sys/class/powercap 2>/dev/null | head -3
dmidecode -s system-product-name 2>/dev/null || cat /sys/class/dmi/id/product_name 2>/dev/null; cat /sys/class/dmi/id/board_name 2>/dev/null
