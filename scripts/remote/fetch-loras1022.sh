#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-loras1022.sh   (newer lightx2v 4-step LoRA pair for Wan 14B image-to-video, 1022 build; about 1.4 GB)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s loras1022" < "$D/fetch-wan.sh"
