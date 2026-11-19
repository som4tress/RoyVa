#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-triton.sh
# EXPERIMENT: Sage 2 image + the comfy-kitchen Triton backend (adds a fast INT8 linear path)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_IMAGE=comfyui-local:v0.42.1-sage2 COMFY_SAGE=1 COMFY_EXTRA=--enable-triton-backend bash "$D/comfy-up.sh"
