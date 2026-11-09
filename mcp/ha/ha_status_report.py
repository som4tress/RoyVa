"""Read-only structured inventory for deterministic tabular rendering."""
import datetime,difflib,re
from collections import Counter
DOMAINS=['light','switch','fan','climate','cover','lock','media_player','vacuum','alarm_control_panel','humidifier','water_heater','sensor','binary_sensor','device_tracker','person']
DEFAULT=DOMAINS[:11]
TOOL={'name':'get_device_status_report','description':'Read current device states as a structured table. Use for device/light status lists, inventories and tabular reports. Omit domains for ALL controllable domains, including media_player, in ONE call; when you pass a name and omit domains, EVERY domain (sensor, binary_sensor, etc.) and diagnostic entities are searched, and the name also matches device, area and entity-id words. Express requested filtering in state/states (multiple states are OR) instead of fetching unfiltered rows for mental filtering. Set include_diagnostics=false to exclude registry diagnostic/config entities. Use the returned counts_by_state and counts_by_area_state for group counts; they cover all matching rows, including rows omitted by limit. Specify sensor/binary_sensor/person/device_tracker explicitly if requested. Scope to a room with area=<area name or id>, or to a whole storey with floor=<floor name or id>; a room named the same as a floor is disambiguated by which of the two parameters is used. No device actions.','inputSchema':{'type':'object','properties':{'domains':{'type':'array','items':{'type':'string','enum':DOMAINS}},'include_diagnostics':{'type':'boolean','description':'Default false: omit entity-registry config/diagnostic categories. Explicit domains are always honored; omitted domains default to controllable domains.'},'name':{'type':'string','description':'Optional words to find (all words must match, any order) in the entity friendly name, entity_id, device name or area. When name is given and domains is omitted, ALL domains are searched, including sensor and binary_sensor. Zero matches returns close-name suggestions.'},'area':{'type':'string','description':'Optional area (room) name or area_id scope.'},'floor':{'type':'string','description':'Optional floor (storey) name or floor_id scope.'},'state':{'type':'string','description':'Optional exact current state, such as on/off/unavailable.'},'states':{'type':'array','items':{'type':'string','minLength':1},'minItems':1,'maxItems':32,'description':'Match any of these exact states (OR). Use instead of state for multiple requested states.'},'limit':{'type':'integer','minimum':1,'maximum':200}},'additionalProperties':False},'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}}


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


def _tokens(text):
 import re
 return [t for t in re.split(r'[^a-z0-9]+',str(text).casefold()) if t]
LIGHT_WORDS={'light','lights','lamp','lamps','tubelight','bulb','chandelier','lighting'}
def _acts_as_light(domain,eid,friendly):
 """Many homes run a light through a smart plug or relay (a switch.* named '... light'); a 'lights' question must include them."""
 return domain=='switch' and bool(LIGHT_WORDS & set(_tokens(friendly)+_tokens(eid.split('.',1)[1])))
def _name_match(name,*fields):
 """Every word of the query must appear in the entity's friendly name, entity_id, device name or area (any order)."""
 q=_tokens(name)
 if not q:return True
 hay=' '.join(_tokens(' '.join(map(str,fields))))
 return all(t in hay for t in q)

def collect(args,read_api):
 if set(args)-{'domains','name','state','limit','include_diagnostics','area','floor','states'}:raise ValueError('Unsupported report filter.')
 name_given=isinstance(args.get('name'),str) and bool(args.get('name').strip())
 searching=name_given
 # A name lookup must never be limited to the controllable domains: sensors, binary sensors, people etc. are searched too.
 domains=args.get('domains',DOMAINS if name_given else DEFAULT)
 if not isinstance(domains,list) or not domains or any(x not in DOMAINS for x in domains):raise ValueError('Invalid domains.')
 diagnostics=args.get('include_diagnostics',searching)
 if type(diagnostics) is not bool:raise ValueError('include_diagnostics must be boolean.')
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
 if area_arg is not None or floor_arg is not None or not diagnostics or searching:
  import ha_registry
  try:registry=ha_registry.snapshot()
  except ValueError:raise
  except Exception as exc:
   if searching and area_arg is None and floor_arg is None and diagnostics:registry=None
   else:raise ValueError('Home Assistant registry unavailable (%s); cannot apply %s scope.'%(type(exc).__name__,'area' if area_arg is not None else 'floor'))
  if floor_arg is not None:scope_floor=_resolve(registry,'floors','floor',floor_arg)
  if area_arg is not None:scope_area=_resolve(registry,'areas','area',area_arg)
 scoped=area_arg is not None or floor_arg is not None
 rows=[]
 for entity in read_api('/api/states'):
  eid=entity.get('entity_id','');domain=eid.split('.')[0];friendly=entity.get('attributes',{}).get('friendly_name',eid)
  as_light='light' in domains and _acts_as_light(domain,eid,friendly)
  if domain not in domains and not as_light:continue
  if as_light and domain not in domains:domain='light'
  rec=registry['entities'].get(eid,{}) if registry else {}
  dev=registry['devices'].get(rec.get('device_id'),{}) if registry else {}
  area_nm=registry['areas'].get(_entity_area(rec,registry['devices']),{}).get('name','') if registry else ''
  if not _name_match(name,friendly,eid,dev.get('name_by_user') or dev.get('name') or '',area_nm):continue
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
 if name and not rows:
  import difflib
  names=[(e.get('attributes',{}).get('friendly_name') or e.get('entity_id','')) for e in read_api('/api/states')]
  out['suggestions']=difflib.get_close_matches(name,names,n=5,cutoff=0.4)
  out['note']='No entity matched in the searched domains %s. Try a different word or check the suggestions; do not tell the user the device does not exist until you have.'%(domains,)
 out['counts_by_state']=dict(Counter(r[2] for r in rows))
 if scoped:out['counts_by_area_state']={area:dict(Counter(r[2] for r in rows if r[3]==area)) for area in sorted(set(r[3] for r in rows))}
 if scoped:out['scope_rule']='Entity area overrides device area; floor membership comes from the area registry.'
 return out
