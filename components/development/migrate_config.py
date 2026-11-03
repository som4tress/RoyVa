from pathlib import Path
import json,os
h=Path.home(); c=h/'.config/opencode'; backup=h/'opencode-migration-backup'
d=json.loads((c/'opencode.json').read_text()); original=json.loads((backup/'evo-config/opencode.json').read_text())
d['providers'].update(original['providers'])
(c/'opencode.json').write_text(json.dumps(d,indent=2)+'\n')
# Keep the existing login password when moving the server.
s=json.loads((c/'service.json').read_text())
p=h/'llm-server/opencode.env';p.write_text('OPENCODE_PASSWORD='+s['password']+'\n');p.chmod(0o600)
s['hostname']='127.0.0.1';s['port']=49374;(c/'service.json').write_text(json.dumps(s))
for name in ['ha','telegram-vision']:
 p=c/f'agents/{name}.md';p.write_text(p.read_text().replace('vllm/qwen38-27b','evo-agent/qwen36-agent' if name=='ha' else 'evo-vision/qwen35-vision'))
p=c/'plugins/ha-mcp-routing/index.js';t=p.read_text().replace("providerID:'vllm',id:'qwen38-27b'","providerID:'evo-agent',id:'qwen36-agent'").replace("providerID!=='vllm'","providerID!=='evo-agent'");p.write_text(t)
p=c/'plugins/ha-mcp-routing/media-routing.js';t=p.read_text().replace("providerID:'vllm',id:'qwen38-27b'","providerID:'evo-vision',id:'qwen35-vision'").replace("providerID==='vllm'","providerID==='evo-vision'");p.write_text(t)
p=c/'lib/media-deadline-proxy.mjs';t=p.read_text().replace("  const target=cloud?", "  if(!cloud)headers.authorization='Bearer '+process.env.VLLM_API_KEY;\n  const ha=req.headers['x-request-kind']==='ha';\n  const payload=cloud?Buffer.concat(chunks):JSON.stringify({...JSON.parse(Buffer.concat(chunks).toString()),model:ha?'qwen36-agent':'qwen35-vision'});\n  const target=cloud?")
t=t.replace("'http://127.0.0.1:8000/v1/chat/completions'","`http://127.0.0.1:${ha?8000:8001}/v1/chat/completions`").replace('body:Buffer.concat(chunks)','body:payload');p.write_text(t)
p=c/'telegram/bridge.mjs';t=p.read_text().replace('const args = ["run",','const args = ["run", "--server", "http://127.0.0.1:49374",').replace('["api","post",','["api","post",');p.write_text(t)
p=c/'scripts/breaking-news-10am.sh';t=p.read_text().replace('source "$BOT_ENV"','source "$BOT_ENV"\nset -a\nsource "$HOME/llm-server/opencode.env"\nsource "$HOME/llm-server/api.env"\nset +a').replace('opencode run \\','opencode run --server http://127.0.0.1:49374 \\');p.write_text(t)
for name in ['opencode-telegram','opencode-media-deadline']:
 p=h/f'.config/systemd/user/{name}.service';t=p.read_text().replace('[Service]','[Service]\nEnvironmentFile=/home/somdutta/llm-server/api.env\nEnvironmentFile=/home/somdutta/llm-server/opencode.env');p.write_text(t)
p=h/'.config/systemd/user/opencode-evo.service';t=p.read_text().replace('WorkingDirectory=/home/somdutta/OpenCodeRunner','WorkingDirectory=/home/somdutta').replace('/home/somdutta/.opencode/bin:/usr/local','/home/somdutta/.opencode/bin:/home/somdutta/.nvm/versions/node/v24.22.1/bin:/usr/local');p.write_text(t)
p=c/'instructions/routing.md';p.write_text(p.read_text()+'\nMigration: local HA tools run on evo-agent/qwen36-agent (128K); image/video analysis runs on evo-vision/qwen35-vision (16K). The old Linux vLLM server is retired. Cloud DeepSeek routing and fallback are preserved. Whisper remains on somdutta-linux and remote voice transcription is not yet connected.\n')
print('Configuration migrated; credentials preserved without display.')
