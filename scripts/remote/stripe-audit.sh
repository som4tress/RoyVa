#!/usr/bin/env bash
# READ-ONLY audit of the 3090 box's data disks before deciding whether two SATA SSDs can be striped: what is on them, what uses them, how big the models are.
# Nothing is written, mounted or formatted. May take up to ~3 minutes on large disks (du/find are time-limited).
# Run:  ! bash ~/RoyVa/scripts/remote/stripe-audit.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s" < "$D/stripe-audit-remote.sh"
