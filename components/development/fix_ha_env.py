from pathlib import Path
h=Path.home()
for n in ['opencode-evo','opencode-telegram']:
 p=h/f'.config/systemd/user/{n}.service';p.write_text(p.read_text().replace('[Service]','[Service]\nEnvironmentFile=/home/somdutta/llm-server/ha.env'))
p=Path('/tmp/verify_integrations.py');t=p.read_text().replace("r=urllib.request.urlopen(urllib.request.Request(url,headers=m['headers']),timeout=15)","import os,re,shlex\nfor line in (h/'llm-server/ha.env').read_text().splitlines():\n k,v=line.split('=',1);os.environ[k]=shlex.split(v)[0]\nheaders={k:re.sub(r'\\{env:([^}]+)\\}',lambda a:os.environ[a[1]],v) for k,v in m['headers'].items()}\nr=urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=15)")
# Earlier instruction replacements were already applied: run only verification section.
t=t[t.index('from pathlib'):];p.write_text(t)
