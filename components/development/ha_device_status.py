"""Bounded, read-only current-state MCP tool. No arbitrary URLs or service calls."""
import re,datetime
TOOL={'name':'get_device_status','description':'Read current HA states for a named device. Use for simple light, switch or fan status. Returns matching friendly names and live states only; cannot control devices.','inputSchema':{'type':'object','properties':{'name':{'type':'string','minLength':2,'description':'Friendly name or distinctive substring; omit domain if unsure how a physical device is exposed.'},'domain':{'type':'array','items':{'type':'string','enum':['light','switch','fan','climate','cover','lock','media_player','binary_sensor','sensor']}}},'required':['name'],'additionalProperties':False},'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}}
def collect(args,read_api):
 if set(args)-{'name','domain'}:raise ValueError('Only name and domain filters are supported.')
 name=args.get('name','');domains=args.get('domain',[])
 if not isinstance(name,str) or len(name.strip())<2:raise ValueError('Specify a distinctive device name.')
 allowed=set(TOOL['inputSchema']['properties']['domain']['items']['enum'])
 if not isinstance(domains,list) or any(d not in allowed for d in domains):raise ValueError('Invalid domain filter.')
 normalize=lambda s:re.sub(r'[^\w]+',' ',s.casefold()).strip()
 needle=normalize(name);matches=[]
 for row in read_api('/api/states'):
  entity=row.get('entity_id','');domain=entity.split('.')[0];attrs=row.get('attributes',{});friendly=attrs.get('friendly_name',entity)
  if domains and domain not in domains:continue
  if needle not in normalize(friendly):continue
  item={'name':friendly,'entity_id':entity,'domain':domain,'state':row.get('state'),'last_changed':row.get('last_changed')}
  for key in ['brightness','percentage','current_temperature','temperature','unit_of_measurement']:
   if key in attrs:item[key]=attrs[key]
  matches.append(item)
 exact=[m for m in matches if normalize(m['name'])==needle]
 if exact:matches=exact
 if len(matches)>20:raise ValueError('Too many matching devices; use a more specific name or domain.')
 return {'source':'Home Assistant current states','as_of':datetime.datetime.now(datetime.timezone.utc).isoformat(),'matches':matches,'count':len(matches),'read_only':True}
