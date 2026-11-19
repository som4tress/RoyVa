#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-int8s2v.sh   (Wan 2.2 speech-to-video 14B INT8 ConvRot, 18.5 GB)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s int8s2v" < "$D/fetch-wan.sh"
