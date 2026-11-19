#!/usr/bin/env bash
# Runs ON the 3090 box. Builds comfyui-local:v0.42.1-cu130 = the ORIGINAL ComfyUI image + PyTorch 2.10 built for CUDA 13.0 (the driver 580 supports it) + a C compiler
# + SageAttention 2 recompiled for CUDA 13. ComfyUI disables its optimized comfy-kitchen CUDA/Triton backends unless torch is built for cu130 or newer.
# The original and the -sage2 images stay untouched. Heavy on CPU for 10-20 minutes (nice 19, 6 cpus, 4 compile jobs). Needs internet and about 15 GB of disk.
set -e
BASE=comfyui-local:v0.42.1; L1=comfyui-local:v0.42.1-cu130-torch; NEW=comfyui-local:v0.42.1-cu130; W="$HOME/comfyui/build130"
mkdir -p "$W/wheels"; rm -f "$W"/wheels/*.whl
CUDA_IMG=""
for t in 13.0.2 13.0.1 13.0.0; do
  if docker pull -q nvidia/cuda:$t-devel-ubuntu22.04 >/dev/null 2>&1; then CUDA_IMG=nvidia/cuda:$t-devel-ubuntu22.04; break; fi
done
[ -n "$CUDA_IMG" ] || { echo "could not pull an nvidia/cuda 13.0 devel image"; exit 1; }
echo "== 1/5 CUDA toolkit image: $CUDA_IMG"; df -h "$HOME" | tail -1
echo "== 2/5 layer: PyTorch 2.10 for CUDA 13.0 + gcc"
cat > "$W/Dockerfile.torch" <<DF
FROM $BASE
USER root
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ git libc6-dev ninja-build && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --force-reinstall --index-url https://download.pytorch.org/whl/cu130 --extra-index-url https://pypi.org/simple torch==2.10.0+cu130 torchvision==0.25.0+cu130
RUN python -c "import torch; print('torch', torch.__version__, 'cuda', torch.version.cuda)"
DF
docker build -q -t "$L1" -f "$W/Dockerfile.torch" "$W"
echo "== 3/5 builder with the CUDA 13 toolkit and the SageAttention source"
cat > "$W/Dockerfile.build" <<DF
FROM $CUDA_IMG AS cuda
FROM $L1
USER root
COPY --from=cuda /usr/local/cuda-13.0 /usr/local/cuda-13.0
RUN git clone --depth 1 https://github.com/thu-ml/SageAttention /src
DF
docker build -q -t comfyui-sagebuild130:tmp -f "$W/Dockerfile.build" "$W"
echo "== 4/5 compiling SageAttention 2 for sm_86 against CUDA 13 (10-20 min, low priority)"
docker run --rm --gpus all --user root --cpus 6 -e CUDA_HOME=/usr/local/cuda-13.0 -e PATH=/usr/local/cuda-13.0/bin:/usr/local/bin:/usr/bin:/bin \
  -e TORCH_CUDA_ARCH_LIST=8.6 -e MAX_JOBS=4 -v "$W/wheels:/wheels" comfyui-sagebuild130:tmp \
  sh -c 'cd /src && nice -n 19 pip wheel --no-build-isolation --no-deps -w /wheels . 2>&1 | tail -12'
ls -l "$W/wheels"; ls "$W"/wheels/*.whl >/dev/null
echo "== 5/5 final image and GPU test (as the container's non-root user, /data mounted)"
cat > "$W/Dockerfile.final" <<DF
FROM $L1
USER root
COPY wheels /wheels
RUN pip install --no-deps --force-reinstall /wheels/*.whl && rm -rf /wheels
DF
docker build -q -t "$NEW" -f "$W/Dockerfile.final" "$W"
docker run --rm --gpus all --user "$(id -u):$(id -g)" --env USER=somdutta --env LOGNAME=somdutta -v "$HOME/comfyui/data:/data" --entrypoint python "$NEW" -c "
import torch, sageattention
from sageattention import sageattn
print('torch', torch.__version__, '| CUDA', torch.version.cuda, '|', torch.cuda.get_device_name(0))
q, k, v = (torch.randn(1, 40, 8192, 128, dtype=torch.float16, device='cuda') for _ in range(3))
o = sageattn(q, k, v, tensor_layout='HND', is_causal=False); ref = torch.nn.functional.scaled_dot_product_attention(q, k, v)
print('sageattn max abs diff vs torch', round(float((o - ref).abs().max()), 4))
import comfy_kitchen as ck
print('comfy_kitchen', {n: (b['available'], b['disabled']) for n, b in ck.list_backends().items()})" 2>&1 | tail -5
docker rmi comfyui-sagebuild130:tmp >/dev/null 2>&1 || true
echo "built $NEW. Start with:  bash ~/RoyVa/scripts/remote/comfy-up-cu130.sh"
