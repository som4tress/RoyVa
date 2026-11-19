#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Read-only: prints the "[perf]" timing lines (from comfy-up-instrument.sh) from the ComfyUI container log on the box.
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-perf.sh [lines, default 150]
ssh ${BOX_SSH} "docker logs comfyui-limited 2>&1 | grep -E '\[perf\]|prepared for dynamic|Requested to load' | tail -${1:-150}"
