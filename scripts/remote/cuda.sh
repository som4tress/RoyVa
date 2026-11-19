#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Run:  ! bash ~/RoyVa/scripts/remote/cuda.sh   (read-only; briefly starts a test container with the GPU)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s" < "$D/inspect-cuda.sh"
