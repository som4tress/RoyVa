#!/usr/bin/env bash
# Runs ON the 3090 box. SageAttention for ComfyUI, installed into the persistent data folder ($HOME/comfyui/data/pylibs), not into the image,
# so it survives container restarts and can be deleted by removing that folder.
#   bash -s inspect   read-only: what the container has (torch, triton, compiler, pip) and what pip would fetch
#   bash -s install   pip install --target pylibs sageattention (low priority), then import test
N=comfyui-limited
case "${1:-inspect}" in
 inspect)
  docker exec $N sh -c 'python -c "import torch;print(\"torch\",torch.__version__,\"cuda\",torch.version.cuda,torch.cuda.get_device_capability())"
    python -c "import triton;print(\"triton\",triton.__version__)" 2>&1 | tail -1
    echo "tools: $(which nvcc gcc cc pip 2>&1 | tr "\n" " ")"
    python -m pip --version 2>&1 | head -1
    python -c "import sageattention;print(\"sageattention already present\")" 2>&1 | tail -1
    echo "--- what pip offers"; python -m pip download sageattention --no-deps -d /tmp/sgdl 2>&1 | tail -4; ls -l /tmp/sgdl 2>/dev/null' ;;
 install)
  mkdir -p "$HOME/comfyui/data/pylibs"
  docker exec $N sh -c 'nice -n 19 python -m pip install --no-deps --target /data/pylibs sageattention 2>&1 | tail -6
    PYTHONPATH=/data/pylibs python -c "import sageattention;print(\"import ok\", getattr(sageattention,\"__version__\",\"\"))" 2>&1 | tail -3' ;;
esac
