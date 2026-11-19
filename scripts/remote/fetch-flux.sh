#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-flux.sh   (FLUX.2 klein 4B fp8 for reference-based image editing; about 4.5 GB; Apache-2.0)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s flux2" < "$D/fetch-wan.sh"
