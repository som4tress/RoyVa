"""Serve the Qwen agent via a pinned llama.cpp Vulkan binary; vLLM stays installed."""
import os
from pathlib import Path
root=Path.home()/'llm-server'
keydir=Path.home()/'.local/state/llamacpp';keydir.mkdir(mode=0o700,parents=True,exist_ok=True)
keyfile=keydir/'api-key';fd=os.open(keyfile,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as f:f.write(os.environ['VLLM_API_KEY']+'\n')
os.environ['LD_LIBRARY_PATH']=str(root/'llamacpp/compat/usr/lib/x86_64-linux-gnu')
binary=str(root/'llamacpp/llama-b12110/llama-server')
args=[binary,'--model',str(root/'models/Qwen3.8-Flash-Next-UD-IQ4_XS/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00004.gguf'),
 '--alias','qwen38-flash-next,qwen38-27b,qwen36-35b','--host','127.0.0.1','--port','8000','--api-key-file',str(keyfile),
 '--override-tensor','per_layer_token_embd[.]weight=CPU','--n-gpu-layers','999','--flash-attn','on','--ctx-size','262144','--parallel','2',
 '--batch-size','2048','--ubatch-size','1024','--threads','8','--threads-batch','16',
 '--jinja','--reasoning','off',
 '--spec-type','draft-mtp','--spec-draft-model','/home/somdutta/llm-server/models/Qwen3.8-Flash-Next-UD-IQ4_XS/MTP/mtp-Qwen3.8-Flash-Next-Q4_K_M.gguf','--spec-draft-ngl','999','--spec-draft-n-max','6','--spec-draft-sampling','probabilistic',
 '--temp','0.7','--top-p','0.8','--top-k','20','--min-p','0','--presence-penalty','1.5','--repeat-penalty','1.0',
 '--cache-prompt','--cache-ram','8192','--metrics','--load-mode','mmap','--fit','off']
os.execv(binary,args)
