#!/usr/bin/env bash
# Runs vm-balloon.sh restore on the 3090 box. Run:  ! bash ~/RoyVa/scripts/remote/vm-restore.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s restore" < "$D/vm-balloon.sh"
