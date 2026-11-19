#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-int8s2v.sh   (Wan 2.2 speech-to-video 14B INT8 ConvRot, 18.5 GB)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s int8s2v" < "$D/fetch-wan.sh"
