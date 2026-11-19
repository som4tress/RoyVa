#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-logs.sh [grep-pattern]   (default: sage|error|warn|oom). Read-only: filters the ComfyUI container log on the 3090 box.
P="${1:-sage|error|warn|oom}"
ssh ${BOX_SSH} "docker logs --tail 400 comfyui-limited 2>&1 | grep -i -E '$P' | tail -25"
