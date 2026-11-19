#!/usr/bin/env bash
# EXPERIMENT (not the default): the locked R4 stack plus --disable-pinned-memory, to test whether the ~19 s before the first step of every sampler call is pinned-memory registration.
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-nopin.sh      Go back with:  ! bash ~/RoyVa/scripts/remote/comfy-up-default.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_IMAGE=comfyui-local:v0.42.1-cu130 COMFY_EXTRA=--enable-triton-backend,--use-ck-attention,--disable-pinned-memory COMFY_DYNAMIC=1 bash "$D/comfy-up.sh"
