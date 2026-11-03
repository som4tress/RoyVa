"""Read-only structured inventory for deterministic tabular rendering."""
import datetime
DOMAINS=['light','switch','fan','climate','cover','lock','media_player','vacuum','alarm_control_panel','humidifier','water_heater','sensor','binary_sensor','device_tracker','person']
DEFAULT=DOMAINS[:11]
TOOL={'name':'get_device_status_report','description':'Read current device states as a structured table. Use for device/light status lists, inventories and tabular reports. Defaults to controllable device domains; specify sensor/binary_sensor/person/device_tracker explicitly if requested. No device actions.','inputSchema':{'type':'object','properties':{'domains':{'type':'array','items':{'type':'string','enum':DOMAINS}},'name':{'type':'string','description':'Optional friendly-name substring.'},'state':{'type':'string','description':'Optional exact current state, such as on/off/unavailable.'},'limit':{'type':'integer','minimum':1,'maximum':200}},'additionalProperties':False},'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}}
def collect(args,read_api):
 if set(args)-{'domains','name','state','limit'}:raise ValueError('Unsupported report filter.')
 domains=args.get('domains',DEFAULT)
 if not isinstance(domains,list) or not domains or any(x not in DOMAINS for x in domains):raise ValueError('Invalid domains.')
 name=args.get('name','');state=args.get('state');limit=args.get('limit',200)
 if not isinstance(name,str) or (state is not None and not isinstance(state,str)) or type(limit) is not int or not 1<=limit<=200:raise ValueError('Invalid report filter or limit.')
 rows=[]
 for entity in read_api('/api/states'):
  eid=entity.get('entity_id','');domain=eid.split('.')[0];friendly=entity.get('attributes',{}).get('friendly_name',eid)
  if domain not in domains or name.casefold() not in friendly.casefold() or (state is not None and entity.get('state')!=state):continue
  rows.append([str(friendly),domain,str(entity.get('state','unknown'))])
 rows.sort(key=lambda r:(r[1],r[0].casefold()))
 return {'kind':'ha_status_report','version':1,'source':'Home Assistant live states','as_of':datetime.datetime.now(datetime.timezone.utc).isoformat(),'domains':domains,'filters':{'name':name,'state':state},'columns':['Device','Type','State'],'rows':rows[:limit],'total':len(rows),'truncated':len(rows)>limit,'read_only':True}
