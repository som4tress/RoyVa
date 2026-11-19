#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-sage.sh
# ComfyUI from the SageAttention-2 image, Sage on, self-restarting, 24 GB cap (same as comfy-up.sh with those options set).
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_IMAGE=comfyui-local:v0.42.1-sage2 COMFY_SAGE=1 bash "$D/comfy-up.sh"
