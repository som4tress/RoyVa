#!/usr/bin/env bash
# Runs vm-balloon.sh status on the 3090 box. Run:  ! bash ~/RoyVa/scripts/remote/vm-status.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s status" < "$D/vm-balloon.sh"
