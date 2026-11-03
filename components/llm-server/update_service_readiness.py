from pathlib import Path

root = Path.home() / 'llm-server'
units = Path.home() / '.config/systemd/user'
for name, port in [('vision', 8001), ('agent', 8000)]:
    unit = units / f'evo-vllm-{name}.service'
    text = unit.read_text()
    if 'ExecStartPost=' not in text:
        text = text.replace('Restart=on-failure', f'ExecStartPost=/usr/bin/python3 {root}/wait_ready.py {port}\nTimeoutStartSec=900\nRestart=on-failure')
    if name == 'agent' and 'After=evo-vllm-vision.service' not in text:
        text = text.replace('[Unit]\n', '[Unit]\nAfter=evo-vllm-vision.service\nWants=evo-vllm-vision.service\n')
    unit.write_text(text)
print('Configured model health checks and sequential startup order.')
