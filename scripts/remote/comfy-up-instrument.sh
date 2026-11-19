#!/usr/bin/env bash
# EXPERIMENT (not the default): the locked R4 stack with timing probes ("[perf]" log lines) mounted read-only over 5 ComfyUI files + 1 new file. Also profiles one warm call each of the high-expert sampler (#3), low-expert sampler (#13), VAE encode (#3) and VAE decode (#3) with torch.profiler; results land in the ComfyUI output folder as perf_profile_*.txt (fetch over HTTP /view?filename=...&type=output).
# Copies the probes to ~/comfyui/instrument on the box, refuses to start if the image's original files differ from the v0.42.1 checksums the probes were written against.
# Run:  ! bash ~/RoyVa/scripts/remote/comfy-up-instrument.sh     Read results:  ! bash ~/RoyVa/scripts/remote/comfy-perf.sh     Go back:  ! bash ~/RoyVa/scripts/remote/comfy-up-default.sh
set -u
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "$D/../../runtime/comfy-instrument" && pwd)"
H=somdutta@somdutta-linux.local
IMAGE=comfyui-local:v0.42.1-cu130
ssh "$H" 'mkdir -p ~/comfyui/instrument/comfy' || exit 1
scp -q "$SRC"/files/comfy/*.py "$H:comfyui/instrument/comfy/" && scp -q "$SRC/original.sha256" "$H:comfyui/instrument/" || exit 1
ssh "$H" "IMAGE=$IMAGE bash -s" <<'R' || exit 1
WD="$(docker image inspect -f '{{.Config.WorkingDir}}' "$IMAGE")"; WD="${WD:-/}"
echo "ComfyUI dir in image: $WD"
while read -r sum rel; do
  got="$(docker run --rm --entrypoint sha256sum "$IMAGE" "$WD/$rel" 2>/dev/null | cut -d' ' -f1)"
  [ "$got" = "$sum" ] || { echo "MISMATCH $rel (image has ${got:-nothing}); not starting"; exit 1; }
done < ~/comfyui/instrument/original.sha256
echo "originals match v0.42.1"
echo "$WD" > ~/comfyui/instrument/workdir
R
WD="$(ssh "$H" 'cat ~/comfyui/instrument/workdir')"
M=""; for f in perf_trace model_patcher pinned_memory model_management samplers sd; do M="$M,/home/somdutta/comfyui/instrument/comfy/$f.py:$WD/comfy/$f.py:ro"; done
COMFY_MOUNTS="${M#,}" COMFY_IMAGE="$IMAGE" COMFY_EXTRA=--enable-triton-backend,--use-ck-attention COMFY_DYNAMIC=1 bash "$D/comfy-up.sh"
