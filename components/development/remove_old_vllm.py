from pathlib import Path
import shutil
h=Path.home().resolve()
for p in [h/'vLLM',h/'.cache/huggingface/hub/models--RedHatAI--Qwen3.8-27B-INT4']:
 assert p.resolve().is_relative_to(h) and p.name in ['vLLM','models--RedHatAI--Qwen3.8-27B-INT4']
 if p.exists(): shutil.rmtree(p); print('Removed',p.name)
p=h/'.config/systemd/user/vllm-qwen27.service'
if p.exists(): p.unlink()
print('Whisper model retained:',bool(list((h/'.local/share/opencode/whisper/models').glob('*.bin'))))
