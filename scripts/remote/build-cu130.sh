#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/build-cu130.sh   (PyTorch for CUDA 13.0 + SageAttention 2 rebuilt: 10-20 min of low-priority CPU, needs internet, about 15 GB disk)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s" < "$D/build-cu130-image.sh"
