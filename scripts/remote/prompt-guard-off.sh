#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Turns the server-side prompt length guard OFF (renames the custom node; nothing is deleted). It takes effect when ComfyUI restarts.
# Back on:  ! bash ~/RoyVa/scripts/remote/prompt-guard.sh   then restart ComfyUI.
#   ! bash ~/RoyVa/scripts/remote/prompt-guard-off.sh && bash ~/RoyVa/scripts/remote/comfy-up-default.sh && bash ~/RoyVa/scripts/remote/prompt-guard-verify.sh
ssh ${BOX_SSH} 'cd ~/comfyui/data/custom_nodes && [ -f prompt_length_guard.py ] && mv prompt_length_guard.py prompt_length_guard.py.disabled && echo "guard disabled (prompt_length_guard.py.disabled); restart ComfyUI to apply" || echo "guard file not found (already off?)"'
