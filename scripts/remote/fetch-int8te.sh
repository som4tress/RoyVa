#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-int8te.sh   (the INT8 umt5 text encoder, 6.7 GB; the Triton backend cannot run the fp8 one on this GPU)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s int8te" < "$D/fetch-wan.sh"
