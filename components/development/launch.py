"""Run one EVO vLLM endpoint; configuration and credentials stay on the host."""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path.home() / 'llm-server'
name = sys.argv[1]
config = json.loads((root / 'servers.json').read_text())
server = config['servers'][name]
command = [
    'docker', 'run', '--rm', '--name', f'evo-vllm-{name}',
    '--network', 'host', '--device', '/dev/kfd', '--device', '/dev/dri',
    '--shm-size', '8g', '--memory', server['host_memory'],
    '--memory-swap', server['host_memory'],
    '-v', f'{Path.home()}/.cache/huggingface:/root/.cache/huggingface',
    '-v', f'{root}/api.env:/run/secrets/api.env:ro',
    '-v', f'{root}/cache:/cache',
    *(['-v', f'{root}/int8-gptq-g128:/models/agent:ro'] if name == 'agent' else []),
    '-e', 'VLLM_ROCM_USE_AITER=0', '-e', 'OMP_NUM_THREADS=8',
    '-e', 'TRITON_CACHE_DIR=/cache/triton',
    '-e', 'TORCHINDUCTOR_CACHE_DIR=/cache/inductor',
    '-e', 'VLLM_CACHE_ROOT=/cache/vllm',
    '-e', 'TOKENIZERS_PARALLELISM=false',
    '--entrypoint', '/bin/bash', config['image'], '-lc',
    'set -a; source /run/secrets/api.env; set +a; exec vllm "$@"',
    'vllm-wrapper', 'serve', server['model'],
    '--served-model-name', server['alias'],
    '--host', '0.0.0.0', '--port', str(server['port']),
    '--dtype', server.get('dtype', 'bfloat16'),
    '--max-model-len', str(server['context']),
    '--max-num-seqs', str(server['concurrency']),
    '--max-num-batched-tokens', '2048',
    '--gpu-memory-utilization', str(server['gpu_fraction']),
    '--reasoning-parser', 'qwen3',
    '--enforce-eager',
    '--enable-prefix-caching' if server.get('prefix_caching', True) else '--no-enable-prefix-caching',
    *(['--kv-cache-memory-bytes', str(server['kv_cache_bytes'])] if 'kv_cache_bytes' in server else []),
    *server['extra_args'],
]
print(f"Starting {name}: {server['model']}; context={server['context']}; active={server['concurrency']}", flush=True)
os.execvp(command[0], command)
