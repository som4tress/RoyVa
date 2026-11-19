#!/usr/bin/env bash
# Read-only: how much RAM does the 3090 box have, what is the ComfyUI container allowed to use, and who else uses RAM (the Home Assistant VM, etc.)? Needed to decide whether both Wan experts (2 x 13.9 GB) can stay in host RAM between jobs.
# Run:  ! bash ~/RoyVa/scripts/remote/box-memory.sh
ssh somdutta@somdutta-linux.local 'echo "--- host:"; free -m | head -3
echo "--- container limits (bytes; 0 = none) and live usage:"; docker inspect comfyui-limited --format "memory={{.HostConfig.Memory}} swap={{.HostConfig.MemorySwap}} cpus={{.HostConfig.NanoCpus}} cpu-shares={{.HostConfig.CpuShares}} restart={{.HostConfig.RestartPolicy.Name}}"
docker stats --no-stream --format "{{.Name}}: mem {{.MemUsage}} ({{.MemPerc}}) cpu {{.CPUPerc}}" 2>/dev/null | head -5
echo "--- biggest RAM users (MB):"; ps -eo rss,args --sort=-rss | head -7 | awk "{printf \"%7.0f  %s\\n\", \$1/1024, substr(\$0, index(\$0,\$2), 90)}"
echo "--- how ComfyUI was started (memory-related flags):"; docker inspect comfyui-limited --format "{{join .Config.Cmd \" \"}} | {{join .HostConfig.Binds \" \"}}" | cut -c1-300'
