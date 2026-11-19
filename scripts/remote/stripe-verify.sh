#!/usr/bin/env bash
# READ-ONLY check of the stripe after stripe-setup (state of fstab/array/mount + cold read speed of old disk vs stripe). Reads about 12 GiB from each disk once (~1 minute); no sudo.
# Run:  ! bash ~/RoyVa/scripts/remote/stripe-verify.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s" < "$D/stripe-verify-remote.sh"
