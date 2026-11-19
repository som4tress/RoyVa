#!/usr/bin/env bash
# Runs ON the 3090 box. Builds comfyui-local:v0.42.1-sage2 = the existing ComfyUI image + a C compiler + SageAttention 2 compiled for the RTX 3090 (sm_86).
# The original image and the -gcc image are untouched. Heavy on CPU for 10-20 minutes (nice 19, 6 cpus, 4 compile jobs). Needs internet and about 12 GB of disk.
# Steps: (1) CUDA 12.8 toolkit stage from nvidia/cuda (ubuntu22.04, glibc old enough for the Debian image), (2) compile the wheel in a GPU container
# (the SageAttention build script probes for a GPU), (3) final image = base + gcc + that wheel, (4) test the kernel on the GPU.
set -e
BASE=comfyui-local:v0.42.1; NEW=comfyui-local:v0.42.1-sage2; W="$HOME/comfyui/build"; CUDA_IMG=nvidia/cuda:12.8.1-devel-ubuntu22.04
mkdir -p "$W/wheels"; rm -f "$W"/wheels/*.whl
echo "== 1/4 builder image"; df -h "$HOME" | tail -1
cat > "$W/Dockerfile.build" <<DF
FROM $CUDA_IMG AS cuda
FROM $BASE
USER root
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ git libc6-dev ninja-build && rm -rf /var/lib/apt/lists/*
COPY --from=cuda /usr/local/cuda-12.8 /usr/local/cuda-12.8
RUN git clone --depth 1 https://github.com/thu-ml/SageAttention /src && cd /src && git log -1 --format='SageAttention commit %h %cd' && (grep -i -m1 license README.md || true)
DF
docker build -q -t comfyui-sagebuild:tmp -f "$W/Dockerfile.build" "$W"
echo "== 2/4 compiling SageAttention 2 for sm_86 (10-20 min, low priority)"
docker run --rm --gpus all --user root --cpus 6 -e CUDA_HOME=/usr/local/cuda-12.8 -e PATH=/usr/local/cuda-12.8/bin:/usr/local/bin:/usr/bin:/bin \
  -e TORCH_CUDA_ARCH_LIST=8.6 -e MAX_JOBS=4 -v "$W/wheels:/wheels" comfyui-sagebuild:tmp \
  sh -c 'cd /src && nice -n 19 pip wheel --no-build-isolation --no-deps -w /wheels . 2>&1 | tail -15'
ls -l "$W/wheels"; ls "$W"/wheels/*.whl >/dev/null
echo "== 3/4 final image"
cat > "$W/Dockerfile.final" <<DF
FROM $BASE
USER root
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && rm -rf /var/lib/apt/lists/*
COPY wheels /wheels
RUN pip install --no-deps /wheels/*.whl && rm -rf /wheels
DF
docker build -q -t "$NEW" -f "$W/Dockerfile.final" "$W"
echo "== 4/4 GPU test as the container's non-root user"
docker run --rm --gpus all --user "$(id -u):$(id -g)" --entrypoint python "$NEW" -c "
import torch, sageattention
from sageattention import sageattn
q = torch.randn(1, 8, 512, 128, dtype=torch.float16, device='cuda')
o = sageattn(q, q, q, tensor_layout='HND', is_causal=False)
ref = torch.nn.functional.scaled_dot_product_attention(q, q, q)
print('sageattention', getattr(sageattention, '__version__', '?'), 'out', tuple(o.shape), 'max abs diff vs torch', float((o - ref).abs().max()))"
docker rmi comfyui-sagebuild:tmp >/dev/null 2>&1 || true
# the old pure-python SageAttention 1 in the data folder would shadow the compiled one (PYTHONPATH wins), so move it aside
[ -d "$HOME/comfyui/data/pylibs" ] && mv "$HOME/comfyui/data/pylibs" "$HOME/comfyui/data/pylibs-sage1" && echo "moved old pylibs to pylibs-sage1"
echo "built $NEW. Start with:  COMFY_IMAGE=$NEW COMFY_SAGE=1 bash ~/RoyVa/scripts/remote/comfy-up.sh"
