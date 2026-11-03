from pathlib import Path
import json,urllib.request,urllib.parse
h=Path.home();c=h/'.config/opencode'
p=c/'instructions/identity.md';t=p.read_text().replace('running on `somdutta-linux`','running on `somdutta-evo`');p.write_text(t)
p=c/'instructions/home-assistant.md';t=p.read_text().replace('This session already runs ON the master host: `somdutta-linux`, user `somdutta`.\n`shivangsh@somdutta-linux.local` is the same physical box (SSH lands on it,','This session runs on `somdutta-evo`, user `somdutta`.\nThe physical speakers remain on the separate machine `shivangsh@somdutta-linux.local` (SSH lands on it,').replace("SSHPASS='<password>' /home/somdutta/.config/opencode/scripts/say-on-host.sh",'/home/somdutta/.config/opencode/scripts/say-on-host.sh');p.write_text(t)
p=c/'instructions/routing.md';t=p.read_text().replace('somdutta-linux.local (2026-10-29)','somdutta-evo.local (migrated 2026-10-31)').replace('vLLM qwen35-9b is only a compatibility alias for the same 27B weights.','The local models are now separate EVO agent and vision endpoints.');p.write_text(t)
d=json.loads((c/'opencode.json').read_text());m=d['mcp']['servers']['home-assistant'];url=m['url'].split('/api/')[0]+'/api/'
r=urllib.request.urlopen(urllib.request.Request(url,headers=m['headers']),timeout=15);print('HA authenticated read:',r.status)
# Verify Telegram identity without sending messages or consuming updates.
env=dict(line.split('=',1) for line in (c/'telegram/bot.env').read_text().splitlines() if line and not line.startswith('#') and '=' in line)
token=env['TELEGRAM_BOT_TOKEN'].strip().strip('"').strip("'")
r=json.load(urllib.request.urlopen('https://api.telegram.org/bot'+token+'/getMe',timeout=15));print('Telegram bot identity verified:',r['ok'])
