#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/sage-install.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s install" < "$D/sage.sh"
