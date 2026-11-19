#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-wan-5b.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s 5b" < "$D/fetch-wan.sh"
