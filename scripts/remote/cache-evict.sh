#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Read-only on the data: drops cached pages of all ComfyUI model files on the box (old disk and /mnt/models) so a test run is a true cold start.
# Run:  ! bash ~/RoyVa/scripts/remote/cache-evict.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s" < "$D/cache-evict-remote.sh"
