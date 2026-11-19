#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# The locked default launcher with the striped model disk mounted over ComfyUI's models folder (/mnt/models -> /data/models, read-only). Use AFTER stripe-setup.sh has completed.
# It REFUSES to start unless /mnt/models is a real mount point on the box and contains the model files (so ComfyUI can never come up on an empty models folder).
# If the stripe is ever not mounted after a reboot, ComfyUI must not run from it: use comfy-up-default.sh (original models on the root disk).
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-stripe.sh
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh ${BOX_SSH} 'mountpoint -q /mnt/models && test -s /mnt/models/diffusion_models/wan2.2_i2v_high_noise_14B_int8_convrot.safetensors && test -s /mnt/models/diffusion_models/qwen_image_2.1_int8_convrot.safetensors' \
  || { echo "REFUSING: /mnt/models is not mounted on the box or the model files are missing. Use comfy-up-default.sh instead."; exit 1; }
COMFY_MOUNTS=/mnt/models:/data/models:ro COMFY_IMAGE=comfyui-local:v0.42.1-cu130 COMFY_EXTRA=--enable-triton-backend,--use-ck-attention COMFY_DYNAMIC=1 bash "$D/comfy-up.sh"

# Proof that ComfyUI really sees the stripe (not the old disk): which device backs /data/models inside the container, the extra model-path config, symlinks, and the mount list.
ssh ${BOX_SSH} "bash -s" <<'R'
echo; echo "== inside the container: device behind /data/models (must be /dev/md0) =="
docker exec comfyui-limited sh -c 'df -h /data/models | tail -1; echo; echo "-- /opt/extra_paths.yaml (extra model search paths):"; cat /opt/extra_paths.yaml 2>&1 | head -30; echo; echo "-- symlinks under /data/models (should be none or point inside the stripe):"; find /data/models -type l 2>/dev/null | head -10; echo "-- top level:"; ls /data/models'
echo; echo "== container mounts =="
docker inspect -f '{{range .Mounts}}{{.Source}} -> {{.Destination}} ({{.Mode}}){{"\n"}}{{end}}' comfyui-limited | grep -E 'models|/data'
R
