"""Bounded, read-only current-state MCP tool. No arbitrary URLs or service calls."""
import re,datetime
def _local(v):
 '''Home Assistant stores UTC; show local time only.'''
 if isinstance(v,str) and len(v)>=19 and v[4:5]=='-' and v[10:11]=='T':
  try:return datetime.datetime.fromisoformat(v.replace('Z','+00:00')).astimezone().isoformat(timespec='seconds')
  except ValueError:pass
 return v
TOOL={'name':'get_device_status','description':'Read current HA states by entity friendly name, or all live entity states belonging to an exact registry device_id from inspect_resources. Use device_id for physical-device telemetry whose sensor names differ from the device name. Returns states, units and HA timestamps; telemetry refresh sensors retain their own reported values. Cannot control devices.','inputSchema':{'type':'object','properties':{'name':{'type':'string','minLength':2,'description':'Entity friendly name or distinctive substring. Specify exactly one of name or device_id; omit domain if unsure how it is exposed.'},'device_id':{'type':'string','minLength':1,'description':'Exact HA device registry ID obtained from discovery. Returns all its live entity states; mutually exclusive with name.'},'domain':{'type':'array','items':{'type':'string','enum':['light','switch','fan','climate','cover','lock','media_player','binary_sensor','sensor','person','device_tracker']}}},'additionalProperties':False},'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}}
def collect(args,read_api):
 if set(args)-{'name','domain','device_id'}:raise ValueError('Only name, device_id and domain filters are supported.')
 name=args.get('name','');device_id=args.get('device_id');domains=args.get('domain',[])
 if ('name' in args)==('device_id' in args):raise ValueError('Specify exactly one of name or device_id.')
 if device_id is not None:
  if not isinstance(device_id,str) or not device_id.strip():raise ValueError('Specify an exact registry device_id.')
  import ha_registry
  registry=ha_registry.snapshot()
  if device_id not in registry['devices']:raise ValueError('Unknown registry device_id; use resource discovery.')
  entity_ids={eid for eid,e in registry['entities'].items() if e.get('device_id')==device_id}
 elif not isinstance(name,str) or len(name.strip())<2:raise ValueError('Specify a distinctive device name.')
 allowed=set(TOOL['inputSchema']['properties']['domain']['items']['enum'])
 if not isinstance(domains,list) or any(d not in allowed for d in domains):raise ValueError('Invalid domain filter.')
 normalize=lambda s:re.sub(r'[^\w]+',' ',s.casefold()).strip()
 needle=normalize(name);matches=[]
 for row in read_api('/api/states'):
  entity=row.get('entity_id','');domain=entity.split('.')[0];attrs=row.get('attributes',{});friendly=attrs.get('friendly_name',entity)
  if domains and domain not in domains:continue
  if device_id is not None:
   if entity not in entity_ids:continue
  elif needle not in normalize(friendly):continue
  item={'name':friendly,'entity_id':entity,'domain':domain,'state':_local(row.get('state')),'last_changed':_local(row.get('last_changed')),'last_updated':_local(row.get('last_updated'))}
  for key in ['brightness','percentage','current_temperature','temperature','unit_of_measurement','device_class']:
   if key in attrs:item[key]=attrs[key]
  if attrs.get('latitude') is not None and attrs.get('longitude') is not None:
   item['latitude']=round(float(attrs['latitude']),6);item['longitude']=round(float(attrs['longitude']),6)
   if attrs.get('gps_accuracy') is not None:item['gps_accuracy']=round(float(attrs['gps_accuracy']),1)
   item['map_url']='https://maps.google.com/?q=%s,%s'%(item['latitude'],item['longitude'])
  matches.append(item)
 exact=[m for m in matches if normalize(m['name'])==needle]
 if device_id is None and exact:matches=exact
 if device_id is None and len(matches)>20:raise ValueError('Too many matching devices; use a more specific name or domain.')
 out={'source':'Home Assistant current states','as_of':datetime.datetime.now(datetime.timezone.utc).isoformat(),'matches':matches,'count':len(matches),'read_only':True}
 if device_id is not None:
  device=registry['devices'][device_id]
  out['device']={'id':device_id,'name':device.get('name_by_user') or device.get('name'),'manufacturer':device.get('manufacturer'),'model':device.get('model')}
  out['registered_entity_count']=len(entity_ids)
  out['missing_state_entity_ids']=sorted(entity_ids-{s['entity_id'] for s in matches}) if not domains else None
  out['domains']=domains or None
 return out
