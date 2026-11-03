import sys,os,json,time,subprocess,datetime
from pathlib import Path
sys.path.insert(0,'/home/somdutta/.config/opencode/mcp')
for name in ['api.env','opencode.env','ha.env']:
 for line in (Path('/home/somdutta/llm-server')/name).read_text().splitlines():
  if '=' in line:
   k,v=line.split('=',1);os.environ[k]=v.strip('"\'')
import ha_registry,ha_history
r=ha_registry.snapshot();states=ha_history.read_api('/api/states')
slim={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host':{'kernel':os.uname().release,'release':dict(line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)},'areas':r['areas'],'floors':r['floors'],'devices':{k:{f:v.get(f) for f in ['id','name','name_by_user','area_id','disabled_by']} for k,v in r['devices'].items()},'entities':{k:{f:v.get(f) for f in ['entity_id','device_id','area_id','entity_category','disabled_by','platform']} for k,v in r['entities'].items()},'states':[{k:s.get(k) for k in ['entity_id','state','last_changed','last_updated']}|{'attributes':{k:v for k,v in s.get('attributes',{}).items() if k in ['friendly_name','brightness','unit_of_measurement','device_class','supported_features']}} for s in states]}
p=Path('/home/somdutta/llm-server/audit15-20261103/truth-latest.json');p.write_text(json.dumps(slim,indent=2));p.chmod(0o600)
print(json.dumps({'states':len(states),'areas':{k:{'name':a.get('name'),'floor_id':a.get('floor_id')} for k,a in r['areas'].items()},'floors':r['floors']}))
