#!/usr/bin/env bash
# Runs comfy-ctl.sh down on the 3090 box. Run:  ! bash ~/RoyVa/scripts/remote/comfy-down.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s down" < "$D/comfy-ctl.sh"
