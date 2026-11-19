#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Run:  ! bash ~/RoyVa/scripts/remote/sage-inspect.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s inspect" < "$D/sage.sh"
