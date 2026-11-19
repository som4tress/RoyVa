#!/usr/bin/env bash
# Runs vm-balloon.sh shrink on the 3090 box. Run:  ! bash ~/RoyVa/scripts/remote/vm-shrink.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s shrink" < "$D/vm-balloon.sh"
