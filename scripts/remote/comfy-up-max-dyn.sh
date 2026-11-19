#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-max-dyn.sh
# Everything in comfy-up-max.sh plus ComfyUI dynamic VRAM (weights stream from disk; no RAM copies)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_IMAGE=comfyui-local:v0.42.1-cu130 COMFY_SAGE=1 COMFY_EXTRA=--enable-triton-backend COMFY_FAST=fp16_accumulation,cublas_ops,autotune COMFY_DYNAMIC=1 bash "$D/comfy-up.sh"
