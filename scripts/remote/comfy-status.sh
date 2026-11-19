#!/usr/bin/env bash
# Runs comfy-ctl.sh status on the 3090 box. Run:  ! bash ~/RoyVa/scripts/remote/comfy-status.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s status" < "$D/comfy-ctl.sh"
