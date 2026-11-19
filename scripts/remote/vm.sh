#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Runs the read-only VM memory check on the 3090 box. Run:  ! bash ~/RoyVa/scripts/remote/vm.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} 'bash -s' < "$D/inspect-vm-memory.sh"
