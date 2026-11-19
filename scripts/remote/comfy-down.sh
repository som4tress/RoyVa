#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Runs comfy-ctl.sh down on the 3090 box. Run:  ! bash ~/RoyVa/scripts/remote/comfy-down.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s down" < "$D/comfy-ctl.sh"
