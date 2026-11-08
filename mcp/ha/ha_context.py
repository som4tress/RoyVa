"""Bounded, read-only current-state and logbook attribution adapter."""
import datetime as dt
from urllib.parse import urlencode,quote
TZ=dt.datetime.now().astimezone().tzinfo     # the host's local zone (not hardcoded), so this works for any household
def local(value):
 '''Home Assistant stores UTC; only local-time text may reach the model.'''
 if isinstance(value,str) and len(value)>=19 and value[4:5]=='-' and value[10:11]=='T':
  try:return dt.datetime.fromisoformat(value.replace('Z','+00:00')).astimezone().isoformat(timespec='seconds')
  except ValueError:pass
 return value
TOOL={'name':'get_on_entities_with_context','description':'List entities that are on right now and the recorded cause of their current on transition. Use for "what entities are on right now and what turned them on", "who turned on the lights", or current active devices with since times. Combines current HA states with exact matching logbook transitions. Reports unknown attribution explicitly. All timestamps are local time. Read-only.','inputSchema':{'type':'object','properties':{'domains':{'type':'array','items':{'type':'string','enum':['light','switch','fan','media_player','climate','input_boolean','binary_sensor','automation','script','lock','cover']},'description':'Optional domains. Omit for every entity with literal state on, plus currently playing media players.'},'lookback_hours':{'type':'integer','minimum':1,'maximum':168,'description':'Logbook window; default 24h. Older on states remain listed with unknown cause.'},'limit':{'type':'integer','minimum':1,'maximum':200,'description':'Maximum returned entities; default 100. Reports truncation.'}},'additionalProperties':False},'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}}
def stamp(value):
 return dt.datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(TZ)
def describe(entry):
 if entry.get('context_domain') in ('automation','script') or entry.get('context_event_type') in ('automation_triggered','script_started'):
  return {'type':entry.get('context_domain') or 'automation','name':entry.get('context_entity_id_name') or entry.get('context_name') or entry.get('context_entity_id'),'entity_id':entry.get('context_entity_id'),'trigger':entry.get('context_source') or entry.get('context_message'),'initiating_user_id':entry.get('context_user_id'),'evidence':'matching logbook transition context'}
 if entry.get('context_user_id'):
  return {'type':'ha_user','user_id':entry['context_user_id'],'service':'.'.join(x for x in [entry.get('context_domain'),entry.get('context_service')] if x),'evidence':'matching logbook transition context','limitation':'User ID is recorded; the client application and human-readable account name are not established.'}
 if entry.get('context_entity_id') or entry.get('context_name'):
  return {'type':'recorded_context','name':entry.get('context_entity_id_name') or entry.get('context_name'),'entity_id':entry.get('context_entity_id'),'evidence':'matching logbook transition context'}
 return {'type':'unknown','reason':'No triggering actor or automation is recorded for this transition.'}
def collect(args,get,now=None):
 now=now or dt.datetime.now(TZ);hours=args.get('lookback_hours',24);limit=args.get('limit',100)
 if type(hours)!=int or not 1<=hours<=168:raise ValueError('lookback_hours must be 1..168')
 if type(limit)!=int or not 1<=limit<=200:raise ValueError('limit must be 1..200')
 domains=args.get('domains')
 if domains is not None and (not isinstance(domains,list) or not all(isinstance(x,str) and x in TOOL['inputSchema']['properties']['domains']['items']['enum'] for x in domains)):raise ValueError('Invalid domains')
 states=get('/api/states')
 selected=[s for s in states if (s.get('state')=='on' or s.get('state')=='playing' and s['entity_id'].startswith('media_player.')) and (domains is None or s['entity_id'].split('.')[0] in domains)]
 selected.sort(key=lambda s:(s['entity_id'].split('.')[0] not in ['light','fan','switch','media_player'],s['entity_id']))
 total=len(selected);selected=selected[:limit];start=now-dt.timedelta(hours=hours);events=[];logbook_error=None
 if selected:
  path='/api/logbook/'+quote(start.isoformat(),safe=':+-')+'?'+urlencode({'end_time':now.isoformat(),'entity':','.join(s['entity_id'] for s in selected)})
  try:events=get(path)
  except Exception as exc:logbook_error=type(exc).__name__+' reading logbook; current states remain available.'
 rows=[]
 for s in selected:
  since=stamp(s['last_changed']);matches=[e for e in events if e.get('entity_id')==s['entity_id'] and e.get('state')==s['state'] and e.get('when') and abs((stamp(e['when'])-since).total_seconds())<=2]
  event=min(matches,key=lambda e:abs((stamp(e['when'])-since).total_seconds())) if matches else None
  cause=describe(event) if event else {'type':'unknown','reason':logbook_error or ('Current on transition predates the requested logbook window.' if since<start else 'No matching transition was found in the logbook window.')}
  row={'entity_id':s['entity_id'],'name':s.get('attributes',{}).get('friendly_name',s['entity_id']),'domain':s['entity_id'].split('.')[0],'state':local(s['state']),'since':since.isoformat(timespec='seconds'),'cause':{k:v for k,v in cause.items() if v is not None}}
  if event:row['matched_event_at']=stamp(event['when']).isoformat(timespec='seconds')
  rows.append(row)
 return {'as_of':now.isoformat(timespec='seconds'),'timezone':str(TZ),'selection':'All literal on states plus playing media; not all device domains use on/off to indicate activity. Configuration/diagnostic toggles are included, not silently removed.','total_matching':total,'returned':len(rows),'truncated':total>limit,'lookback_hours':hours,'entities':rows,'logbook_error':logbook_error,'limitations':['Causes are based only on logbook entries matching the actual current transition within two seconds.','Current state context may describe a later attribute update; it is not reused as proof of who turned the entity on.','Unknown causes remain unknown. A recorded HA user ID does not identify the client app.']}
