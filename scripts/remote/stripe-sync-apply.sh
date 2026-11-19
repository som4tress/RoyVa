#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Copies the model files that exist on the old disk but are missing on the stripe (the 4 Qwen-Image 2.1 files). No sudo: /mnt/models is owned by the box user.
# If a subfolder turns out to be root-owned, rsync reports "Permission denied" for it and nothing is half-written (rsync uses temp files).
# Run:  ! bash ~/RoyVa/scripts/remote/stripe-sync-apply.sh
ssh ${BOX_SSH} "rsync -av --bwlimit=200m --ignore-existing ~/comfyui/data/models/ /mnt/models/ 2>&1 | tail -25"
