#!/usr/bin/env bash
# Runs comfy-ctl.sh up on the 3090 box. Run:  ! bash ~/RoyVa/scripts/remote/comfy-up.sh
# Options pass through:  ! COMFY_SAGE=1 bash ~/RoyVa/scripts/remote/comfy-up.sh   (also COMFY_MEM=40g, COMFY_CPUS=8)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "COMFY_SAGE=${COMFY_SAGE:-0} COMFY_MEM=${COMFY_MEM:-24g} COMFY_CPUS=${COMFY_CPUS:-8} COMFY_IMAGE=${COMFY_IMAGE:-comfyui-local:v0.42.1} COMFY_RESTART=${COMFY_RESTART:-1} COMFY_DYNAMIC=${COMFY_DYNAMIC:-0} COMFY_FAST=${COMFY_FAST:-} COMFY_EXTRA=${COMFY_EXTRA:-} COMFY_ENV=${COMFY_ENV:-} COMFY_CUDA_MALLOC=${COMFY_CUDA_MALLOC:-0} COMFY_MOUNTS=${COMFY_MOUNTS:-} bash -s up" < "$D/comfy-ctl.sh"
