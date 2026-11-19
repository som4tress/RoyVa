#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-wan-5b.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s 5b" < "$D/fetch-wan.sh"
