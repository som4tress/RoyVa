#!/usr/bin/env bash
# Read-only on the data: drops cached pages of all ComfyUI model files on the box (old disk and /mnt/models) so a test run is a true cold start.
# Run:  ! bash ~/RoyVa/scripts/remote/cache-evict.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s" < "$D/cache-evict-remote.sh"
