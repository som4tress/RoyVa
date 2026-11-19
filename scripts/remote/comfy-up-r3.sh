#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-r3.sh
# R3: INT8 base (cu130 + Sage 2 + Triton backend) + --highvram, dynamic VRAM off
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_IMAGE=comfyui-local:v0.42.1-cu130 COMFY_SAGE=1 COMFY_EXTRA=--enable-triton-backend,--highvram COMFY_DYNAMIC=1 bash "$D/comfy-up.sh"
