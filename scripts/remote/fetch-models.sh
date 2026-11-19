#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Run:  ! bash ~/RoyVa/scripts/remote/fetch-models.sh        (Hunyuan 1.5 + Wan 14B image-to-video, about 75 GB)
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} "bash -s hunyuan 14b-i2v" < "$D/fetch-wan.sh"
