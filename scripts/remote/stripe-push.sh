#!/usr/bin/env bash
# Copies the stripe setup script to the 3090 box (nothing is run, nothing changes there). Then, in a REAL terminal (sudo asks for your password, which our wrappers cannot type):
#   ssh -t somdutta@somdutta-linux.local 'sudo bash ~/stripe-setup.sh'            (dry run: checks only)
#   ssh -t somdutta@somdutta-linux.local 'sudo bash ~/stripe-setup.sh --apply'    (for real, after you read the dry run)
# Run:  ! bash ~/RoyVa/scripts/remote/stripe-push.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
scp -q "$D/stripe-setup-remote.sh" somdutta@somdutta-linux.local:stripe-setup.sh && echo "copied to the box as ~/stripe-setup.sh (not run)"
