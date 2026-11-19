#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-loras.sh   (4-step speed LoRAs: Wan 14B image-to-video x2, Hunyuan 1.5; about 3 GB)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s loras" < "$D/fetch-wan.sh"
