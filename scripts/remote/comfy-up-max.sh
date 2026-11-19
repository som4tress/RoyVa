#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-max.sh
# CUDA 13 image + Sage 2 + Triton backend + --fast fp16_accumulation,cublas_ops,autotune (dynamic VRAM left off)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_IMAGE=comfyui-local:v0.42.1-cu130 COMFY_SAGE=1 COMFY_EXTRA=--enable-triton-backend COMFY_FAST=fp16_accumulation,cublas_ops,autotune bash "$D/comfy-up.sh"
