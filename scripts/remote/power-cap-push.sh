#!/usr/bin/env bash
# Copies the GPU power-cap installer to the 3090 box (nothing is run, nothing changes there). Then, in a REAL terminal (sudo asks for your password, which our wrappers cannot type):
#   ssh -t somdutta@somdutta-linux.local 'sudo bash ~/install-boot-service.sh 300'
# That installs gpu-power-limit.service: at every boot it enables persistence mode and caps the RTX 3090 at 300 W. Undo is in the header of install-boot-service.sh.
# Run:  ! bash ~/RoyVa/scripts/remote/power-cap-push.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
scp -q "$D/install-boot-service.sh" somdutta@somdutta-linux.local:install-boot-service.sh && echo "copied to the box as ~/install-boot-service.sh (not run)"
