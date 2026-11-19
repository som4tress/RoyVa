#!/usr/bin/env bash
# READ-ONLY, runs on the 3090 box: was the ComfyUI container killed for memory, and when? Also lists ComfyUI's cache options.
echo "== container state"; docker inspect -f 'OOMKilled={{.State.OOMKilled}} ExitCode={{.State.ExitCode}} Started={{.State.StartedAt}} Finished={{.State.FinishedAt}} Restart={{.HostConfig.RestartPolicy.Name}} Mem={{.HostConfig.Memory}}' comfyui-limited
echo; echo "== kernel OOM events, last 3 hours"
journalctl -k --since "3 hours ago" --no-pager 2>/dev/null | grep -i -E "out of memory|oom-kill|killed process" | cut -c1-230 | tail -8
echo; echo "== box uptime / now"; uptime; date
echo; echo "== last ComfyUI log lines before it stopped"; docker logs --tail 12 comfyui-limited 2>&1 | cut -c1-200
echo; echo "== cache-related ComfyUI options in this image"
docker run --rm --entrypoint python comfyui-local:v0.42.1-sage2 main.py --help 2>&1 | grep -i -E "cache|ram|lru" | cut -c1-200
