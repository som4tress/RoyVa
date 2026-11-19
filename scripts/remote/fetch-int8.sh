#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-int8.sh   (Wan 2.2 14B image-to-video INT8 ConvRot, high + low noise, about 29 GB, Apache-2.0)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s int8" < "$D/fetch-wan.sh"
