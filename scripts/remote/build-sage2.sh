#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/build-sage2.sh   (compiles SageAttention 2 into a copy of the ComfyUI image: 10-20 min of low-priority CPU, needs internet and about 12 GB disk)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s" < "$D/build-sage2-image.sh"
