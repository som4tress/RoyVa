import os,sys,json,re,pathlib
h=pathlib.Path.home()
for line in (h/'llm-server/ha.env').read_text().splitlines():
 if '=' in line and not line.startswith('#'):
  k,v=line.split('=',1);os.environ[k.strip()]=v.strip().strip('\"\'')
sys.path.insert(0,str(h/'.config/opencode/mcp'))
import ha_history as ha
states=ha.read_api('/api/states');rows=[r for r in states if re.search(r'stove|cooktop|burner|range|oven',r['entity_id']+' '+str(r.get('attributes',{}).get('friendly_name','')),re.I)]
(h/'llm-server/ha-appliance-status-20261103/appliance-states.json').write_text(json.dumps(rows,indent=2));(h/'llm-server/ha-appliance-status-20261103/appliance-states.json').chmod(0o600)
for r in rows:print(json.dumps(r))
