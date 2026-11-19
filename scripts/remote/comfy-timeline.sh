#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Read-only: timestamped phase markers from the ComfyUI container log (prompt start, model loads, dynamic-VRAM prepare, prompt done), to see where the ~45 s before the GPU computes goes.
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-timeline.sh [lines, default 60]
ssh ${BOX_SSH} "docker logs --timestamps comfyui-limited 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E 'got prompt|Requested to load|prepared for dynamic|Prompt executed|loaded completely|Unloading|models unloaded|WARNING|OOM' | cut -c1-170 | tail -${1:-60}"
