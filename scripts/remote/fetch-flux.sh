#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-flux.sh   (FLUX.2 klein 4B fp8 for reference-based image editing; about 4.5 GB; Apache-2.0)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s flux2" < "$D/fetch-wan.sh"
