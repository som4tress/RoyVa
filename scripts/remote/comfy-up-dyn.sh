#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-dyn.sh
# Like comfy-up-sage.sh but with ComfyUI dynamic VRAM on (weights stream from disk; keeps RAM use low). EXPERIMENT: use it to see if the out-of-memory kills stop and what it does to speed.
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_IMAGE=comfyui-local:v0.42.1-sage2 COMFY_SAGE=1 COMFY_DYNAMIC=1 bash "$D/comfy-up.sh"
