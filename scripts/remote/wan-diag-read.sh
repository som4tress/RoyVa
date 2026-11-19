#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Read-only: prints the Wan timing diagnostic lines from the ComfyUI container log on the 3090 box. Optional argument: a grep pattern (default: all [wan_timing_diag] lines, last 150).
# Run:  ! bash ~/RoyVa/scripts/remote/wan-diag-read.sh        or        ! bash ~/RoyVa/scripts/remote/wan-diag-read.sh installed
P="${1:-.}"
ssh ${BOX_SSH} "docker logs comfyui-limited 2>&1 | grep 'wan_timing_diag' | grep -E '$P' | tail -150 | cut -c1-330"
