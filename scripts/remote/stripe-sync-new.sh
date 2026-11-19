#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Lists (dry run, default, no sudo) or copies (--apply, needs a real terminal for sudo) model files on the old disk that are missing on the stripe.
# Dry run:  ! bash ~/RoyVa/scripts/remote/stripe-sync-new.sh
# Copy:     in a REAL terminal:  bash ~/RoyVa/scripts/remote/stripe-sync-new.sh --apply
if [ "$1" = "--apply" ]; then
  ssh -t ${BOX_SSH} "sudo rsync -av --progress --bwlimit=200m --ignore-existing ~/comfyui/data/models/ /mnt/models/ | tail -25"
else
  ssh ${BOX_SSH} "rsync -avn --ignore-existing ~/comfyui/data/models/ /mnt/models/ | tail -25"
fi
