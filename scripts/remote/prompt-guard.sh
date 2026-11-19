#!/usr/bin/env bash
# Copies the server-side prompt length guard to the 3090 box. Nothing is restarted and nothing else changes there.
# Then, when the GPU is idle: restart ComfyUI with your usual launcher (it only loads custom nodes at start), and verify:
#   ! bash ~/RoyVa/scripts/remote/prompt-guard.sh            (this script: copies the file)
#   ! bash ~/RoyVa/scripts/remote/comfy-up-default.sh        (restart ComfyUI)
#   ! bash ~/RoyVa/scripts/remote/prompt-guard-verify.sh     (proves the guard is active)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local 'mkdir -p ~/comfyui/data/custom_nodes' && scp -q "$D/comfy-prompt-guard/prompt_length_guard.py" somdutta@somdutta-linux.local:comfyui/data/custom_nodes/prompt_length_guard.py && echo "copied to ~/comfyui/data/custom_nodes/prompt_length_guard.py (not active until ComfyUI restarts)"
