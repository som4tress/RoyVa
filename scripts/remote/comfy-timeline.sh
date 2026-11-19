#!/usr/bin/env bash
# Read-only: timestamped phase markers from the ComfyUI container log (prompt start, model loads, dynamic-VRAM prepare, prompt done), to see where the ~45 s before the GPU computes goes.
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-timeline.sh [lines, default 60]
ssh somdutta@somdutta-linux.local "docker logs --timestamps comfyui-limited 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E 'got prompt|Requested to load|prepared for dynamic|Prompt executed|loaded completely|Unloading|models unloaded|WARNING|OOM' | cut -c1-170 | tail -${1:-60}"
