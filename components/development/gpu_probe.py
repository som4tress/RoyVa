import json
import torch
import vllm

print('vLLM:', vllm.__version__)
print('PyTorch:', torch.__version__, 'HIP:', torch.version.hip)
if not torch.version.hip:
    raise RuntimeError('This probe requires a ROCm PyTorch build; run it inside the AMD container.')
print('GPU available:', torch.cuda.is_available())
print('GPU:', torch.cuda.get_device_name(0))
print('Properties:', torch.cuda.get_device_properties(0))
print('Free/total GPU GiB:', [round(x / 2**30, 2) for x in torch.cuda.mem_get_info()])
x = torch.randn((1024, 1024), device='cuda', dtype=torch.bfloat16)
y = x @ x
torch.cuda.synchronize()
print('BF16 matrix multiplication:', y.shape, bool(torch.isfinite(y).all()))
