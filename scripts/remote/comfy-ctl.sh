#!/usr/bin/env bash
# Start / stop / inspect ComfyUI on the 3090 box with hard limits, so it cannot starve the class, homework or the Home Assistant VM.
# Uses the existing image and models (~/comfyui/data). Leaves the old containers (comfyui, comfyui-before-memory-fix) alone.
# Restarts itself after a reboot or crash (docker --restart unless-stopped); 'down' keeps it stopped until the next 'up'. COMFY_RESTART=0 turns that off.
# An idle ComfyUI only holds the web server and a few hundred MB; the GPU and RAM are used when a picture is generated, within the limits below.
# Usage (on the box):  bash comfy-ctl.sh up | down | status
set -u
NAME=comfyui-limited
IMAGE="${COMFY_IMAGE:-comfyui-local:v0.42.1}"   # COMFY_IMAGE=comfyui-local:v0.42.1-gcc adds a C compiler (needed for SageAttention, see build-gcc-image.sh)
DATA="$HOME/comfyui/data"
MEM="${COMFY_MEM:-24g}"     # hard cap on RAM, and the same for memory+swap (no swap spill). Host: 47 GB, VMs now ~9 GB, ~28 GB available; this leaves ~4 GB for the desktop and his Chrome
ENVV="${COMFY_ENV:-}"   # container environment variables, comma-separated KEY=VALUE, e.g. PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
CMALLOC="${COMFY_CUDA_MALLOC:-0}"   # 1 = let ComfyUI use its default CUDA allocator (drops --disable-cuda-malloc)
EXTRA="${COMFY_EXTRA:-}"   # extra ComfyUI arguments, comma-separated so they survive ssh, e.g. COMFY_EXTRA=--enable-triton-backend,--use-ck-attention
FAST="${COMFY_FAST:-}"   # e.g. COMFY_FAST="fp16_accumulation" -> ComfyUI --fast fp16_accumulation (fp16 matmuls accumulate in fp16: about 2x the matmul rate on GeForce cards; check the output for artifacts)
DYN="${COMFY_DYNAMIC:-0}"   # 1 = ComfyUI dynamic VRAM (streams weights from disk instead of holding full copies in RAM; meant for models bigger than memory)
RESTART="${COMFY_RESTART:-1}"
SAGE="${COMFY_SAGE:-0}"    # 1 = start ComfyUI with --use-sage-attention (needs the sageattention package in $DATA/pylibs, see sage.sh)
CPUS="${COMFY_CPUS:-8}"    # of 12 cores; --cpu-shares 256 (below) makes the desktop and VMs win whenever cores are contended
case "${1:-status}" in
  up)
    case "$IMAGE" in *sage2*) ;; *) [ -d "$DATA/pylibs" ] && PYLIBS=1 ;; esac   # the old pure-python SageAttention 1 in pylibs would shadow the compiled one in the sage2 image
    [ "$SAGE" = 1 ] && SAGE_FLAG="--use-sage-attention"
    [ "$RESTART" = 1 ] && RESTART_FLAG="--restart unless-stopped"
    [ -n "$FAST" ] && SAGE_FLAG="${SAGE_FLAG:-} --fast ${FAST//,/ }"
    [ -n "$EXTRA" ] && SAGE_FLAG="${SAGE_FLAG:-} ${EXTRA//,/ }"
    ENV_FLAGS=""; for kv in ${ENVV//,/ }; do ENV_FLAGS="$ENV_FLAGS --env $kv"; done
    MOUNT_FLAGS=""; M_LIST="${COMFY_MOUNTS:-}"; for m in ${M_LIST//,/ }; do MOUNT_FLAGS="$MOUNT_FLAGS -v $m"; done   # COMFY_MOUNTS=host:container[:ro],... extra bind mounts (used by comfy-up-instrument.sh)
    if [ "$DYN" = 1 ]; then VRAM_FLAGS="--enable-dynamic-vram --disable-cuda-malloc --vram-headroom 2"; else VRAM_FLAGS="--disable-dynamic-vram --disable-cuda-malloc --reserve-vram 2"; fi
    [ "$CMALLOC" = 1 ] && VRAM_FLAGS="${VRAM_FLAGS//--disable-cuda-malloc/}"
    docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "image $IMAGE is missing"; exit 1; }
    [ -d "$DATA/models" ] || { echo "no models folder at $DATA/models"; exit 1; }
    if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then docker rm -f "$NAME" >/dev/null; fi
    docker run -d --name "$NAME" --gpus all ${RESTART_FLAG:-} ${ENV_FLAGS:-} \
      --memory "$MEM" --memory-swap "$MEM" --cpus "$CPUS" --cpu-shares 256 --pids-limit 512 \
      ${PYLIBS:+--env PYTHONPATH=/data/pylibs} --env USER="$(id -un)" --env LOGNAME="$(id -un)" --env TORCHINDUCTOR_CACHE_DIR=/data/user/.cache/torchinductor \
      --user "$(id -u):$(id -g)" --security-opt no-new-privileges:true --cap-drop ALL --shm-size 1g \
      --log-opt max-size=10m --log-opt max-file=3 \
      -p 8188:8188 -v "$DATA:/data" ${MOUNT_FLAGS:-} "$IMAGE" \
      python main.py --listen 0.0.0.0 --port 8188 --base-directory /data --extra-model-paths-config /opt/extra_paths.yaml \
      ${VRAM_FLAGS} ${SAGE_FLAG:-} || exit 1
    for i in $(seq 1 40); do
      if curl -fsS http://127.0.0.1:8188/system_stats >/dev/null 2>&1; then echo "ComfyUI is up (took ~$((i*2))s)"; break; fi
      sleep 2
    done
    docker logs --tail 5 "$NAME" 2>&1
    ;;
  down)  docker stop -t 20 "$NAME" && docker rm "$NAME" && echo stopped ;;
  status)
    docker ps -a --filter "name=$NAME" --format 'container {{.Names}}: {{.Status}}'
    docker stats --no-stream --format 'cpu {{.CPUPerc}}  mem {{.MemUsage}} ({{.MemPerc}})' "$NAME" 2>/dev/null
    curl -fsS http://127.0.0.1:8188/system_stats 2>/dev/null | head -c 600; echo
    nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw --format=csv,noheader
    ;;
  *) echo "usage: $0 up|down|status"; exit 2 ;;
esac
