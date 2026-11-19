#!/usr/bin/env bash
# READ-ONLY inspection of the old ComfyUI Docker setup on the 3090 box. Changes nothing, starts nothing.
# Run from the Claude terminal:  ! ssh somdutta@somdutta-linux.local 'bash -s' < ~/RoyVa/scripts/remote/inspect-comfyui.sh
cd ~/comfyui || exit 1
echo "=== Dockerfile ==="; cat Dockerfile
echo "=== start.sh ==="; cat start.sh
echo "=== start-before-memory-fix.sh ==="; cat start-before-memory-fix.sh
echo "=== data/ ==="; ls -la data 2>&1 | head -20
echo "=== models sizes ==="; du -sh data/models/* 2>&1
echo "=== model files ==="; ls -la data/models/checkpoints data/models/diffusion_models data/models/text_encoders data/models/vae 2>&1 | head -40
echo "=== container limits and exit reason ==="
for c in comfyui comfyui-before-memory-fix; do
  echo "-- $c"; docker inspect "$c" --format 'mem_limit={{.HostConfig.Memory}} oom_killed={{.State.OOMKilled}} exit={{.State.ExitCode}} finished={{.State.FinishedAt}} restart={{.HostConfig.RestartPolicy.Name}} ports={{json .HostConfig.PortBindings}}' 2>&1
done
echo "=== images ==="; docker images --format '{{.Repository}}:{{.Tag}} {{.Size}}' 2>&1 | head -10
echo "=== kernel OOM history (if readable) ==="; journalctl -k --since "-30 days" 2>/dev/null | grep -i -E "out of memory|oom-kill|killed process" | tail -5 || true
echo "=== memory ==="; free -h; swapon --show
echo "=== VM memory settings ==="; virsh list --all 2>&1 | head;
