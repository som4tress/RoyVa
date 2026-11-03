"""Read-only structured inventory for deterministic tabular rendering."""
import datetime
from collections import Counter
DOMAINS=['light','switch','fan','climate','cover','lock','media_player','vacuum','alarm_control_panel','humidifier','water_heater','sensor','binary_sensor','device_tracker','person']
DEFAULT=DOMAINS[:11]
TOOL={'name':'get_device_status_report','description':'Read current device states as a structured table. Use for device/light status lists, inventories and tabular reports. Omit domains for ALL controllable domains, including media_player, in ONE call. Express requested filtering in state/states (multiple states are OR) instead of fetching unfiltered rows for mental filtering. Set include_diagnostics=false to exclude registry diagnostic/config entities. Use the returned counts_by_state and counts_by_area_state for group counts; they cover all matching rows, including rows omitted by limit. Specify sensor/binary_sensor/person/device_tracker explicitly if requested. Scope to a room with area=<area name or id>, or to a whole storey with floor=<floor name or id>; a room named the same as a floor is disambiguated by which of the two parameters is used. No device actions.','inputSchema':{'type':'object','properties':{'domains':{'type':'array','items':{'type':'string','enum':DOMAINS}},'include_diagnostics':{'type':'boolean','description':'Default false: omit sensor/tracker/person domains and entity-registry config/diagnostic categories. Set true only when those domains or all HA entities are explicitly requested.'},'name':{'type':'string','description':'Optional friendly-name substring.'},'area':{'type':'string','description':'Optional area (room) name or area_id scope.'},'floor':{'type':'string','description':'Optional floor (storey) name or floor_id scope.'},'state':{'type':'string','description':'Optional exact current state, such as on/off/unavailable.'},'states':{'type':'array','items':{'type':'string','minLength':1},'minItems':1,'maxItems':32,'description':'Match any of these exact states (OR). Use instead of state for multiple requested states.'},'limit':{'type':'integer','minimum':1,'maximum':200}},'additionalProperties':False},'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}}


def _resolve(registry,pool_key,kind,value):
 keys=registry[pool_key]
 key=value.strip().casefold()
 hits=[k for k,v in keys.items() if k.casefold()==key or str(v.get('name','')).strip().casefold()==key]
 if len(hits)==1:return hits[0]
 if not hits:raise ValueError('No %s named %r.'%(kind,value.strip()))
 raise ValueError('Ambiguous %s %r: matches %s.'%(kind,value.strip(),', '.join(sorted(hits))))


def _entity_area(entity,devices):
 area=entity.get('area_id')
 if not area and entity.get('device_id'):area=devices.get(entity['device_id'],{}).get('area_id')
 return area


def collect(args,read_api):
 if set(args)-{'domains','name','state','limit','include_diagnostics','area','floor','states'}:raise ValueError('Unsupported report filter.')
 domains=args.get('domains',DEFAULT)
 if not isinstance(domains,list) or not domains or any(x not in DOMAINS for x in domains):raise ValueError('Invalid domains.')
 diagnostics=args.get('include_diagnostics',False)
 if type(diagnostics) is not bool:raise ValueError('include_diagnostics must be boolean.')
 if not diagnostics:domains=[d for d in domains if d in DEFAULT]
 name=args.get('name','');state=args.get('state');limit=args.get('limit',200)
 if isinstance(state,str) and state.strip().lower() in ['', 'any', 'all', '*']:state=None
 if not isinstance(name,str) or (state is not None and not isinstance(state,str)) or type(limit) is not int or not 1<=limit<=200:raise ValueError('Invalid report filter or limit.')
 states=args.get('states')
 if states is not None:
  if not isinstance(states,list) or not 1<=len(states)<=32 or any(not isinstance(x,str) or not x.strip() for x in states):raise ValueError('Invalid states filter.')
  if state is not None:raise ValueError('Use state or states, not both.')
  states=list(dict.fromkeys(x.strip() for x in states))
 area_arg=args.get('area');floor_arg=args.get('floor')
 for label,value in (('area',area_arg),('floor',floor_arg)):
  if value is not None and (not isinstance(value,str) or not value.strip()):raise ValueError('Invalid %s scope.'%label)
 registry=None;scope_area=None;scope_floor=None
 if area_arg is not None or floor_arg is not None or not diagnostics:
  import ha_registry
  try:registry=ha_registry.snapshot()
  except ValueError:raise
  except Exception as exc:raise ValueError('Home Assistant registry unavailable (%s); cannot apply %s scope.'%(type(exc).__name__,'area' if area_arg is not None else 'floor'))
  if floor_arg is not None:scope_floor=_resolve(registry,'floors','floor',floor_arg)
  if area_arg is not None:scope_area=_resolve(registry,'areas','area',area_arg)
 scoped=area_arg is not None or floor_arg is not None
 rows=[]
 for entity in read_api('/api/states'):
  eid=entity.get('entity_id','');domain=eid.split('.')[0];friendly=entity.get('attributes',{}).get('friendly_name',eid)
  if domain not in domains or name.casefold() not in friendly.casefold():continue
  if not diagnostics and registry['entities'].get(eid,{}).get('entity_category') in ['config','diagnostic']:continue
  area_id=None
  if scoped:
   record=registry['entities'].get(eid,{})
   area_id=_entity_area(record,registry['devices'])
   if not area_id:continue
   if scope_area is not None and area_id!=scope_area:continue
   if scope_floor is not None and registry['areas'].get(area_id,{}).get('floor_id')!=scope_floor:continue
  label=registry['areas'].get(area_id,{}).get('name') if scoped and area_id else ''
  rows.append([str(friendly),domain,str(entity.get('state','unknown'))]+([str(label)] if scoped else []))
 if name:
  exact=[r for r in rows if r[0].strip().casefold()==name.strip().casefold()]
  if exact:rows=exact
 if state is not None:rows=[r for r in rows if r[2]==state]
 if states is not None:rows=[r for r in rows if r[2] in states]
 rows.sort(key=lambda r:(r[1],r[0].casefold()))
 filters={'name':name,'state':state,'states':states,'include_diagnostics':diagnostics,'limit':limit}
 if scoped:
  filters['area']=registry['areas'].get(scope_area,{}).get('name') if scope_area else None
  filters['floor']=registry['floors'].get(scope_floor,{}).get('name') if scope_floor else None
 out={'kind':'ha_status_report','version':1,'source':'Home Assistant live states','as_of':datetime.datetime.now(datetime.timezone.utc).isoformat(),'domains':domains,'filters':filters,'columns':['Device','Type','State','Area'] if scoped else ['Device','Type','State'],'rows':rows[:limit],'total':len(rows),'truncated':len(rows)>limit,'read_only':True}
 out['counts_by_state']=dict(Counter(r[2] for r in rows))
 if scoped:out['counts_by_area_state']={area:dict(Counter(r[2] for r in rows if r[3]==area)) for area in sorted(set(r[3] for r in rows))}
 if scoped:out['scope_rule']='Entity area overrides device area; floor membership comes from the area registry.'
 return out
