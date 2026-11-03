from pathlib import Path
h=Path.home();c=h/'.config/opencode'
for name in ['opencode-telegram','opencode-media-deadline']:
 p=h/f'.config/systemd/user/{name}.service';t=p.read_text().replace('[Service]','[Service]\nEnvironmentFile=/home/somdutta/llm-server/api.env\nEnvironmentFile=/home/somdutta/llm-server/opencode.env');p.write_text(t)
p=h/'.config/systemd/user/opencode-evo.service';t=p.read_text().replace('WorkingDirectory=/home/somdutta/OpenCodeRunner','WorkingDirectory=/home/somdutta').replace('/home/somdutta/.opencode/bin:/usr/local','/home/somdutta/.opencode/bin:/home/somdutta/.nvm/versions/node/v24.22.1/bin:/usr/local');p.write_text(t)
p=c/'instructions/routing.md';p.write_text(p.read_text()+'\nMigration: local HA tools use evo-agent/qwen36-agent (128K); image/video analysis uses evo-vision/qwen35-vision (16K). Old Linux vLLM is retired. Cloud routing and fallback are preserved. Whisper remains on somdutta-linux, with remote transcription deferred.\n')
