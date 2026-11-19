#!/usr/bin/env bash
# READ-ONLY, runs on the 3090 box: which CUDA / PyTorch / kernel libraries does the ComfyUI image really have, and what does ComfyUI say about optimized CUDA operations?
IMG="${1:-comfyui-local:v0.42.1-sage2}"
echo "== host driver"; nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv,noheader; nvidia-smi | grep -i "CUDA Version"
echo; echo "== image: torch / CUDA / kernels"
docker run --rm --gpus all --entrypoint sh "$IMG" -c '
python - <<PY
import torch
print("torch", torch.__version__, "| built for CUDA", torch.version.cuda, "| cudnn", torch.backends.cudnn.version(), "| device", torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))
try:
    import comfy_kitchen as ck
    print("comfy_kitchen", getattr(ck, "__version__", "?"))
    for n in ("list_backends", "available_backends", "get_backends"):
        if hasattr(ck, n):
            print(" ", n, getattr(ck, n)())
except Exception as e:
    print("comfy_kitchen: not importable:", str(e)[:120])
PY
echo "--- relevant packages"; pip list 2>/dev/null | grep -i -E "^(torch|torchvision|torchaudio|triton|comfy|sageattention|flash|xformers|nvidia-cuda|nvidia-cublas|nvidia-cudnn)" '
echo; echo "== what ComfyUI printed at startup about CUDA"
docker logs comfyui-limited 2>&1 | grep -i -E "cu130|cuda|pytorch version|optimized|comfy.kitchen|backend" | head -12 | cut -c1-200
