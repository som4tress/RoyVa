from pathlib import Path
import subprocess,json
h=Path.home();units=h/'.config/systemd/user'
for name,port in [('news',8765),('sonosp',8770)]:
 p=units/f'opencode-audio-{name}.service';p.write_text(f'[Unit]\nDescription=OpenCode {name} audio files\nAfter=network-online.target\n[Service]\nExecStart=/usr/bin/python3 -m http.server {port} --bind 0.0.0.0 --directory /home/somdutta/media/{name}\nRestart=on-failure\n[Install]\nWantedBy=default.target\n')
p=h/'.config/opencode/instructions/home-assistant.md';p.write_text(p.read_text()+'\nGenerated news and Sonos audio files are now hosted on EVO: http://192.168.4.191:8765/ (~/media/news) and http://192.168.4.191:8770/ (~/media/sonosp). Use these directories and URLs for new playback assets.\n')
s=(h/'llm-server/migration-ha-test.jsonl').read_text()
for line in s.splitlines():
 try:
  d=json.loads(line);p=d.get('part',{});
  if 'tool' in d.get('type','') or p.get('type')=='tool':print('Tool event:',p.get('tool'),p.get('state',{}).get('status'))
 except:pass
print('Migration request output saved.')
