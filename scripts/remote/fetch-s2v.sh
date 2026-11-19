#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-s2v.sh   (Wan 2.2 speech-to-video 14B fp8 + audio encoder + 4-step LoRA, about 18 GB)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s s2v" < "$D/fetch-wan.sh"
