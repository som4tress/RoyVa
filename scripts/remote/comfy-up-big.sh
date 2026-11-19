#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-big.sh
# EXPERIMENT: like comfy-up-sage.sh but with a 36 GB RAM cap so both 14B experts (about 28 GB together) can stay in memory. The box has about 36 GB available when idle; the cap is a ceiling, not a reservation.
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFY_MEM=36g COMFY_IMAGE=comfyui-local:v0.42.1-sage2 COMFY_SAGE=1 bash "$D/comfy-up.sh"
