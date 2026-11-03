import os
from pathlib import Path

root = Path.home() / 'llm-server'
image = 'rocm/vllm:rocm7.13.0_gfx1151_ubuntu24.04_py3.13_pytorch_2.10.0_vllm_0.19.1'
command = [
    'docker', 'run', '--rm', '--name', 'evo-int8-compat', '--network', 'host',
    '--device', '/dev/kfd', '--device', '/dev/dri',
    '--shm-size', '4g', '--memory', '8g', '--memory-swap', '8g',
    '-v', f'{root}:/workspace:ro',
    '-v', f'{root}/cache:/cache',
    '-e', 'VLLM_ROCM_USE_AITER=0', '-e', 'OMP_NUM_THREADS=8',
    '-e', 'TRITON_CACHE_DIR=/cache/triton',
    '-e', 'TORCHINDUCTOR_CACHE_DIR=/cache/inductor',
    '--entrypoint', 'vllm', image,
    'serve', '/workspace/int8-candidate', '--load-format', 'dummy',
    '--served-model-name', 'compatibility-test-not-a-real-model',
    '--host', '127.0.0.1', '--port', '8010', '--dtype', 'half',
    '--max-model-len', '131072', '--max-num-seqs', '2',
    '--max-num-batched-tokens', '2048', '--gpu-memory-utilization', '0.65',
    '--kv-cache-memory-bytes', '25769803776', '--enable-prefix-caching',
    '--language-model-only', '--enforce-eager',
    '--attention-backend', 'TRITON_ATTN',
]
os.execvp(command[0], command)
