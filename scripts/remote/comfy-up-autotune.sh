#!/usr/bin/env bash
# EXPERIMENT (not the default): the locked R4 stack plus "--fast autotune" ONLY (sets torch cudnn.benchmark; nothing else from the --fast bundle), to see if the Wan VAE's 3D convolutions (image encode ~2.3 s and decode+save ~4.4 s per clip) get faster.
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-autotune.sh      Go back with:  ! bash ~/RoyVa/scripts/remote/comfy-up-default.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_IMAGE=comfyui-local:v0.42.1-cu130 COMFY_EXTRA=--enable-triton-backend,--use-ck-attention COMFY_FAST=autotune COMFY_DYNAMIC=1 bash "$D/comfy-up.sh"
