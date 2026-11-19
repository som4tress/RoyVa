#!/usr/bin/env bash
# READ-ONLY, runs on the 3090 box: what is using memory and disk. Changes nothing, starts no GPU work.
echo "== memory (free -h)"; free -h
echo; echo "== top 10 processes by memory (RSS)"; ps -eo rss,pmem,comm,args --sort=-rss | head -11 | awk 'NR==1{print "RSS_MB  %MEM  COMMAND"} NR>1{printf "%6d  %4s  %s\n", $1/1024, $2, substr($0, index($0,$3), 90)}'
echo; echo "== containers: memory now / limit"; docker stats --no-stream --format '{{.Name}}  {{.MemUsage}}  ({{.MemPerc}})' 2>&1 | head -8
echo; echo "== VMs: configured vs used (virsh)"; for vm in $(virsh list --all --name); do echo -n "$vm: "; virsh dominfo "$vm" 2>&1 | grep -E "Max memory|Used memory" | tr -s ' ' | tr '\n' ' '; echo; done
echo; echo "== disks (df -h, real filesystems only)"; df -h -x tmpfs -x devtmpfs -x squashfs -x overlay 2>/dev/null | cut -c1-110
echo; echo "== Docker disk use"; docker system df 2>&1 | head -6
echo; echo "== biggest places under $HOME (depth 2, may take up to a minute)"; timeout 60 du -xh --max-depth=2 "$HOME" 2>/dev/null | sort -rh | head -12
echo; echo "== other big places readable without sudo"; for d in /var/log /var/lib/libvirt/images /var/cache /swapfile; do [ -e "$d" ] && timeout 20 du -xsh "$d" 2>/dev/null; done
echo; echo "== swap"; swapon --show 2>/dev/null
