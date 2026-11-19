#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-r1.sh
# R1: base (INT8 setup) + --fast fp16_accumulation,cublas_ops,autotune + --preview-method none + default CUDA allocator + expandable_segments
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_IMAGE=comfyui-local:v0.42.1-cu130 COMFY_SAGE=1 COMFY_EXTRA=--enable-triton-backend,--preview-method,none COMFY_FAST=fp16_accumulation,cublas_ops,autotune COMFY_CUDA_MALLOC=1 COMFY_ENV=PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True bash "$D/comfy-up.sh"
