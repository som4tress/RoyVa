#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-cu130-triton.sh
# CUDA 13 image: Sage 2 + the comfy-kitchen Triton backend, nothing else (INT8-only test)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_IMAGE=comfyui-local:v0.42.1-cu130 COMFY_SAGE=1 COMFY_EXTRA=--enable-triton-backend bash "$D/comfy-up.sh"
