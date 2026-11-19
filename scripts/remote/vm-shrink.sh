#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Runs vm-balloon.sh shrink on the 3090 box. Run:  ! bash ~/RoyVa/scripts/remote/vm-shrink.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s shrink" < "$D/vm-balloon.sh"
