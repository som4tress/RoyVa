import json,pathlib
p=pathlib.Path.home()/'ha-local-debug/openapi.json';d=json.loads(p.read_text());s=d.get('components',{}).get('schemas',{})
for k,v in s.items():
 if 'mcp' in k.lower() or 'tool' in k.lower() and 'config' in k.lower():print(k,str(v)[:1200])
print([k for k in d.get('paths',{}) if 'config' in k or 'tool' in k])
