#!/usr/bin/env bash
# Runs the read-only VM memory check on the 3090 box. Run:  ! bash ~/RoyVa/scripts/remote/vm.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local 'bash -s' < "$D/inspect-vm-memory.sh"
