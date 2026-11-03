from pathlib import Path
import secrets

root = Path.home() / 'llm-server'
key_file = root / 'api.env'
if not key_file.exists():
    key_file.write_text('VLLM_API_KEY=' + secrets.token_urlsafe(32) + '\n')
key_file.chmod(0o600)
units = Path.home() / '.config/systemd/user'
units.mkdir(parents=True, exist_ok=True)
for name in ('agent', 'vision'):
    target = units / f'evo-vllm-{name}.service'
    if target.exists():
        raise RuntimeError(f'Refusing to overwrite existing unit: {target}')
    target.write_text(f'''[Unit]
Description=EVO vLLM {name} endpoint
StartLimitIntervalSec=600
StartLimitBurst=2

[Service]
Type=simple
WorkingDirectory={root}
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 {root}/launch.py {name}
ExecStop=-/usr/bin/docker stop -t 30 evo-vllm-{name}
Restart=on-failure
RestartSec=15
TimeoutStopSec=60

[Install]
WantedBy=default.target
''')
print('Created protected API credential and inactive user service definitions.')
