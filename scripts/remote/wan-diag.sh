#!/usr/bin/env bash
# Copies the READ-ONLY Wan timing diagnostic node to the 3090 box. Nothing is restarted. It only loads when ComfyUI restarts (see below). It changes no behaviour: it writes timing lines to ComfyUI's own log.
# Run, when the GPU is idle:
#   ! bash ~/RoyVa/scripts/remote/wan-diag.sh            (this script: copies the file)
#   ! bash ~/RoyVa/scripts/remote/comfy-up-default.sh    (restart ComfyUI; it starts from the striped disk)
#   ! bash ~/RoyVa/scripts/remote/wan-diag-read.sh installed   (proves the hook is active)
# After a Wan test:  ! bash ~/RoyVa/scripts/remote/wan-diag-read.sh      Off without restart:  ! bash ~/RoyVa/scripts/remote/wan-diag-toggle.sh off   (on: same with "on")
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local 'mkdir -p ~/comfyui/data/custom_nodes' && scp -q "$D/comfy-wan-diag/wan_timing_diag.py" somdutta@somdutta-linux.local:comfyui/data/custom_nodes/wan_timing_diag.py && echo "copied to ~/comfyui/data/custom_nodes/wan_timing_diag.py (not active until ComfyUI restarts)"
