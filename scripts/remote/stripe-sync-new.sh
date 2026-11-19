#!/usr/bin/env bash
# Lists (dry run, default, no sudo) or copies (--apply, needs a real terminal for sudo) model files on the old disk that are missing on the stripe.
# Dry run:  ! bash ~/RoyVa/scripts/remote/stripe-sync-new.sh
# Copy:     in a REAL terminal:  bash ~/RoyVa/scripts/remote/stripe-sync-new.sh --apply
if [ "$1" = "--apply" ]; then
  ssh -t somdutta@somdutta-linux.local "sudo rsync -av --progress --bwlimit=200m --ignore-existing ~/comfyui/data/models/ /mnt/models/ | tail -25"
else
  ssh somdutta@somdutta-linux.local "rsync -avn --ignore-existing ~/comfyui/data/models/ /mnt/models/ | tail -25"
fi
