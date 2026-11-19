#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-ltx.sh     (LTX-2 19B distilled fp8 + Gemma encoder + upscaler, about 36 GB)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s ltx2" < "$D/fetch-wan.sh"
