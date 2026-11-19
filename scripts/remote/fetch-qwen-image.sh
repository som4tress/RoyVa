#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-qwen-image.sh   (Qwen-Image 2.1 INT8 ConvRot 7.3 GB + Qwen3-VL-8B INT8 text encoder 9.4 GB + VAE 0.7 GB + Lightning 4-step LoRA 0.07 GB; resumable)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s qwen21" < "$D/fetch-wan.sh"
