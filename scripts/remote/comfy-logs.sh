#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-logs.sh [grep-pattern]   (default: sage|error|warn|oom). Read-only: filters the ComfyUI container log on the 3090 box.
P="${1:-sage|error|warn|oom}"
ssh somdutta@somdutta-linux.local "docker logs --tail 400 comfyui-limited 2>&1 | grep -i -E '$P' | tail -25"
