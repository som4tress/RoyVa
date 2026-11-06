"""Serve Qwen3.6 35B Q8_0 for the RoyVa production evaluation."""
import os
from pathlib import Path
root=Path.home()/'llm-server'
keydir=Path.home()/'.local/state/llamacpp';keydir.mkdir(mode=0o700,parents=True,exist_ok=True)
keyfile=keydir/'api-key';fd=os.open(keyfile,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as f:f.write(os.environ['VLLM_API_KEY']+'\n')
os.environ['LD_LIBRARY_PATH']=str(root/'llamacpp/compat/usr/lib/x86_64-linux-gnu')
binary=str(root/'llamacpp/llama-b12110/llama-server')
args = [binary,
    '--model', str(root/'models/Qwen3.6-35B-A3B-Q8_0.gguf'),
    '--mmproj', str(root/'models/mmproj-Qwen3.6-F16.gguf'),
    '--image-min-tokens', '1024',
    '--alias', 'qwen36-35b,qwen38-flash-next,qwen38-27b',
    '--host', '127.0.0.1', '--port', '8000', '--api-key-file', str(keyfile),
    '--n-gpu-layers', '999', '--flash-attn', 'on', '--ctx-size', '262144', '--parallel', '2',
    '--batch-size', '2048', '--ubatch-size', '1024', '--threads', '8', '--threads-batch', '16',
    '--jinja', '--reasoning', 'off',
    '--temp', '0.7', '--top-p', '0.8', '--top-k', '20', '--min-p', '0',
    '--presence-penalty', '1.5', '--repeat-penalty', '1.0',
    '--cache-prompt', '--cache-ram', '8192', '--metrics', '--load-mode', 'mmap', '--fit', 'off']
os.execv(binary,args)
