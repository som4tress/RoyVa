#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/changes.sh   (read-only)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s" < "$D/inspect-changes.sh"
