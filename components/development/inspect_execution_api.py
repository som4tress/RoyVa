import json,pathlib
p=pathlib.Path.home()/'ha-local-debug/openapi.json';d=json.loads(p.read_text())
for path,item in d['paths'].items():
 if 'session' in path and any(w in path for w in ['synthetic','message','prompt','interrupt','context']):print(path,','.join(item))
for key,v in d.get('components',{}).get('schemas',{}).items():
 if 'Synthetic' in key:print(key,str(v)[:1000])
