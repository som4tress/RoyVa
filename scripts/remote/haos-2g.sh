#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Run:  ! bash ~/RoyVa/scripts/remote/haos-2g.sh check     (read-only)
#       ! bash ~/RoyVa/scripts/remote/haos-2g.sh apply     (shuts Haos down, resizes to 2 GiB, restarts: Home Assistant offline 1-2 min)
#       ! bash ~/RoyVa/scripts/remote/haos-2g.sh restore   (back to the saved 16 GiB definition)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s ${1:-check}" < "$D/vm-haos-2g.sh"
