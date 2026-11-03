from pathlib import Path
import sys,hashlib,json
sys.path.insert(0,str(Path.home()/'.config/opencode/mcp'))
import ha_template_runner as r
for q in ['Turn den light off.','Turn den light on.','Turn Hall Lamp on']:
 print(repr(q),r.standalone(q,True),hashlib.sha256(q.lower().rstrip('.').encode()).hexdigest())
 try:print(r.checked_args(r.OFF if 'off' in q else r.ON,{'name':'Den Switch' if 'den' in q else 'Hall Lamp','domain':['light']},q))
 except Exception as e:print(str(e))
