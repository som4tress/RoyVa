import json,pathlib
p=pathlib.Path.home()/'.config/opencode/opencode.json'
d=json.loads(p.read_text())
def clean(x):
 if isinstance(x,dict): return {k: ('REDACTED' if any(s in k.lower() for s in ['key','authorization','password','token']) else clean(v)) for k,v in x.items()}
 if isinstance(x,list): return [clean(v) for v in x]
 return x
print(json.dumps(clean(d.get('providers')),indent=2))
