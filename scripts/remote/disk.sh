#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/disk.sh   (read-only, reads 3 GB from the disk for a few seconds)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s" < "$D/inspect-disk.sh"
