import json
from pathlib import Path
import secrets

root = Path.home() / 'llm-server'
config_dir = Path.home() / '.config/opencode'
config_dir.mkdir(parents=True, exist_ok=True)
config_path = config_dir / 'opencode.json'
if config_path.exists():
    raise RuntimeError('Existing OpenCode config needs inspection before modification')
config_path.write_text(json.dumps({
    '$schema': 'https://opencode.ai/config.json',
    'model': 'evo-agent/qwen36-agent',
    'providers': {
        'evo-agent': {
            'name': 'EVO Qwen 35B Agent',
            'package': '@opencode/ai/providers/openai-compatible',
            'settings': {'baseURL': 'http://127.0.0.1:8000/v1', 'apiKey': '{env:VLLM_API_KEY}'},
            'models': {
                'qwen36-agent': {
                    'name': 'Qwen3.6 35B Agent (128K)',
                    'capabilities': {'tools': True, 'input': ['text'], 'output': ['text']},
                    'limit': {'context': 131072, 'output': 8192},
                    'compatibility': {'reasoningField': 'reasoning_content'},
                    'body': {'chat_template_kwargs': {'enable_thinking': True}}
                }
            }
        }
    }
}, indent=2) + '\n')
env_file = root / 'opencode.env'
if not env_file.exists():
    env_file.write_text('OPENCODE_PASSWORD=' + secrets.token_urlsafe(24) + '\n')
env_file.chmod(0o600)
project = Path.home() / 'OpenCodeRunner'
project.mkdir(exist_ok=True)
unit = Path.home() / '.config/systemd/user/opencode-evo.service'
if unit.exists():
    raise RuntimeError('Existing OpenCode unit needs inspection')
unit.write_text(f'''[Unit]
Description=OpenCode EVO runner
StartLimitIntervalSec=300
StartLimitBurst=3

[Service]
Type=simple
WorkingDirectory={project}
Environment=PATH={Path.home()}/.opencode/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile={root}/api.env
EnvironmentFile={root}/opencode.env
ExecStart={Path.home()}/.opencode/bin/opencode serve --hostname 0.0.0.0 --port 49374
Restart=on-failure
RestartSec=10
UMask=0077

[Install]
WantedBy=default.target
''')
print('Prepared OpenCode model configuration and inactive service; credentials stored privately.')
