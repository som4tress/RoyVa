#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/verify.sh   (read-only checklist of the running ComfyUI; run after every launch)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s" < "$D/verify-comfy.sh"
