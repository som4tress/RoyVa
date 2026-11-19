#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-loras.sh   (4-step speed LoRAs: Wan 14B image-to-video x2, Hunyuan 1.5; about 3 GB)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh somdutta@somdutta-linux.local "bash -s loras" < "$D/fetch-wan.sh"
