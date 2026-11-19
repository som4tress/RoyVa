#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Run:  ! bash ~/RoyVa/scripts/remote/build-gcc.sh   (adds a C compiler to a copy of the ComfyUI image, about 1 minute, needs internet on the box)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s" < "$D/build-gcc-image.sh"
