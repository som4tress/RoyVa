#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/sage-test.sh   (under a minute; briefly uses the GPU)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s" < "$D/sage-test-image.sh"
