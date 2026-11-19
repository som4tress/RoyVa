#!/usr/bin/env bash
# The locked default launcher (measured best, "R4"): cu130 image, dynamic VRAM, Triton backend, CK attention. Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-default.sh
# Not used: --highvram (4% faster but risks a GPU out-of-memory), Sage attention (slower than CK here).
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 2026-11-18 owner rule: ComfyUI must start with its models on the striped disk. This launcher now delegates to comfy-up-stripe.sh (which refuses if the stripe is not mounted);
# the old single-disk start is only available explicitly: COMFY_NO_STRIPE=1 bash comfy-up-default.sh
[ -z "$COMFY_NO_STRIPE" ] && exec bash "$D/comfy-up-stripe.sh"
COMFY_IMAGE=comfyui-local:v0.42.1-cu130 COMFY_EXTRA=--enable-triton-backend,--use-ck-attention COMFY_DYNAMIC=1 bash "$D/comfy-up.sh"
