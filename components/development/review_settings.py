from pathlib import Path
import json,re
h=Path.home();d=json.loads((h/'.config/opencode/opencode.json').read_text())
print('Default model:',d.get('model'));print('Instructions:',[Path(x).name for x in d.get('instructions',[])]);print('Providers:',list(d.get('providers',{})))
p=h/'.config/opencode/scripts/openrouter-usage';s=p.read_text();print('Usage helper lines:',len(s.splitlines()))
for n,l in enumerate(s.splitlines(),1):
 if any(t in l for t in ['mark','session','requests.get','urlopen','urllib','generation','SELECT','last_id','sqlite','ledger']):
  safe=re.sub(r'sk-[A-Za-z0-9_-]+','REDACTED',l);print(str(n)+': '+safe[:200])
