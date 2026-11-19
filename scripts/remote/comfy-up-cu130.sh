#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-cu130.sh
# CUDA 13 image: Sage 2 on, fp16 accumulation on; ComfyUI should now enable its comfy-kitchen CUDA backend
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_IMAGE=comfyui-local:v0.42.1-cu130 COMFY_SAGE=1 COMFY_FAST=fp16_accumulation bash "$D/comfy-up.sh"
