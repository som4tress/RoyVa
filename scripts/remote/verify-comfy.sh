#!/usr/bin/env bash
# READ-ONLY checklist, runs on the 3090 box, for the running ComfyUI container. Run it after every launch.
N=comfyui-limited
ok() { echo "  [ok]    $1"; }; bad() { echo "  [CHECK] $1"; }
echo "== container"; docker ps -a --filter "name=$N" --format '  {{.Names}}: {{.Status}}  image {{.Image}}'
docker inspect -f '  restart policy={{.HostConfig.RestartPolicy.Name}}  memory cap={{.HostConfig.Memory}}  OOMKilled={{.State.OOMKilled}}' $N
ARGS=$(docker inspect -f '{{join .Args " "}}' $N)
echo "  args: $ARGS"
echo "== checklist"
case "$ARGS" in *--use-sage-attention*) ok "started with --use-sage-attention";; *) bad "no --use-sage-attention flag";; esac
LOG=$(docker logs $N 2>&1)
CU=$(docker exec $N python -c "import torch;print(torch.version.cuda)" 2>/dev/null)
case "$CU" in 13*) ok "PyTorch built for CUDA $CU";; *) bad "PyTorch built for CUDA '$CU' (ComfyUI wants 13.0 or newer for its optimized kernels)";; esac
echo "$LOG" | grep -q "cu130 or higher" && bad "ComfyUI still warns: needs pytorch with cu130 or higher" || ok "no cu130 warning"
echo "$LOG" | grep -q "Using sage attention" && ok "log says: Using sage attention" || bad "log does not say 'Using sage attention'"
echo "$LOG" | grep -q "Error running sage attention" && bad "Sage attention errors in the log (falling back to PyTorch attention)" || ok "no 'Error running sage attention' lines (appear at first use)"
for b in cuda triton eager; do
  L=$(echo "$LOG" | grep "Found comfy_kitchen backend $b:" | head -1)
  [ -z "$L" ] && { bad "backend $b: not mentioned in the log"; continue; }
  A=$(echo "$L" | grep -o "'available': [A-Za-z]*" | head -1); D=$(echo "$L" | grep -o "'disabled': [A-Za-z]*" | head -1)
  if echo "$D" | grep -q True; then bad "comfy_kitchen backend $b: $A, $D"; else ok "comfy_kitchen backend $b: $A, $D"; fi
done
echo "== Sage kernel smoke test inside the running container (small, about 1 s on the GPU)"
docker exec $N python -c "
import torch, sageattention
from sageattention import sageattn
q, k, v = (torch.randn(1, 8, 1024, 128, dtype=torch.float16, device='cuda') for _ in range(3))
o = sageattn(q, k, v, tensor_layout='HND', is_causal=False); ref = torch.nn.functional.scaled_dot_product_attention(q, k, v)
print('  sageattn ok, max abs diff vs torch', round(float((o - ref).abs().max()), 4), '| torch', torch.__version__)" 2>&1 | tail -2
echo "== warnings and errors in the startup log"
echo "$LOG" | grep -E "WARNING|ERROR|Traceback" | cut -c1-200 | head -8
echo "== done"
