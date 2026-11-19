#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Runs comfy-ctl.sh status on the 3090 box. Run:  ! bash ~/RoyVa/scripts/remote/comfy-status.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s status" < "$D/comfy-ctl.sh"
