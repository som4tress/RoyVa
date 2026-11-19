#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/cuda.sh   (read-only; briefly starts a test container with the GPU)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s" < "$D/inspect-cuda.sh"
