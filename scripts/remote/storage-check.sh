#!/usr/bin/env bash
# Read-only: do we have an NVMe / M.2 drive on the 3090 box, what else is in it, and what disk do the ComfyUI models sit on?
# Run:  ! bash ~/RoyVa/scripts/remote/storage-check.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s" < "$D/storage-check-remote.sh"
