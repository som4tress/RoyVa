exec(open('/home/somdutta/llm-server/ha-appliance-status-20261103/inspect.py').read().split("states=ha.read_api")[0])
import ha_registry
reg=ha_registry.snapshot();states=ha.read_api('/api/states')
for r in states:
 keys=[k for k in r.get('attributes',{}) if re.search('burner|cooktop|stove',k,re.I)]
 if keys:print('ATTRIBUTE_MATCH',r['entity_id'],{k:r['attributes'][k] for k in keys})
related=[e for e in reg['entities'].values() if re.search('stove|cooktop|burner|satv173380p',e['entity_id']+' '+str(e.get('original_name',''))+' '+str(e.get('name','')),re.I)]
for e in related:print(json.dumps({k:e.get(k) for k in ['entity_id','original_name','name','platform','disabled_by','hidden_by','device_id']}))
ids={e.get('device_id') for e in related}
for id in ids:
 d=reg['devices'].get(id,{})
 if d:print('DEVICE',json.dumps({k:d.get(k) for k in ['id','name','name_by_user','manufacturer','model','model_id','sw_version']}))
