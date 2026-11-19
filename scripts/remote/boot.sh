#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/boot.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s" < "$D/inspect-boot.sh"
