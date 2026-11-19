#!/usr/bin/env bash
# Runs ON the 3090 box. GPU smoke test of comfyui-local:v0.42.1-sage2 the way the real container runs (non-root user, /data mounted for the Triton cache).
# Shows which SageAttention kernel the auto-dispatch picks on this GPU, the error against PyTorch attention, and a timing of both. Takes under a minute; uses the GPU briefly.
IMG="${1:-comfyui-local:v0.42.1-sage2}"
docker run --rm --gpus all --user "$(id -u):$(id -g)" --env USER="$(id -un)" --env LOGNAME="$(id -un)" -v "$HOME/comfyui/data:/data" --entrypoint python "$IMG" -c "
import time, torch, sageattention
from sageattention import sageattn
print('sageattention', sageattention.__file__)
B, H, N, D = 1, 40, 8192, 128      # about the size of one Wan attention layer on a 5 s clip
q, k, v = (torch.randn(B, H, N, D, dtype=torch.float16, device='cuda') for _ in range(3))
ref = torch.nn.functional.scaled_dot_product_attention(q, k, v)
o = sageattn(q, k, v, tensor_layout='HND', is_causal=False)
print('out', tuple(o.shape), 'max abs diff vs torch', round(float((o - ref).abs().max()), 4), 'mean abs diff', round(float((o - ref).abs().mean()), 5))
def bench(f, n=10):
    f(); torch.cuda.synchronize(); t = time.time()
    for _ in range(n): f()
    torch.cuda.synchronize(); return (time.time() - t) / n * 1000
print('torch sdpa ms', round(bench(lambda: torch.nn.functional.scaled_dot_product_attention(q, k, v)), 1))
print('sageattn   ms', round(bench(lambda: sageattn(q, k, v, tensor_layout='HND', is_causal=False)), 1))
" 2>&1 | tail -12
