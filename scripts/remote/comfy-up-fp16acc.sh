#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-fp16acc.sh
# EXPERIMENT: Sage 2 image + ComfyUI --fast fp16_accumulation (fp16 matmuls accumulate in fp16: up to 2x matmul rate on GeForce; check the picture)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_IMAGE=comfyui-local:v0.42.1-sage2 COMFY_SAGE=1 COMFY_FAST=fp16_accumulation bash "$D/comfy-up.sh"
