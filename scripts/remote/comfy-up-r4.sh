#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-r4.sh
# R4: INT8 base (cu130 + Triton backend) with ComfyUI's own comfy-kitchen attention (--use-ck-attention) instead of Sage 2
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_IMAGE=comfyui-local:v0.42.1-cu130 COMFY_EXTRA=--enable-triton-backend,--use-ck-attention COMFY_DYNAMIC=1 bash "$D/comfy-up.sh"
