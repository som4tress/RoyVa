#!/usr/bin/env python3
"""Narrow, read-only Home Assistant recorded zone-history MCP server."""
import datetime as dt
import json, os, re, sys, urllib.request, urllib.parse
from pathlib import Path
from zoneinfo import ZoneInfo
TZ=ZoneInfo('America/Los_Angeles')
from ha_context import TOOL as CONTEXT_TOOL, collect as collect_context
from ha_device_status import TOOL as STATUS_TOOL, collect as collect_status
from ha_status_report import TOOL as REPORT_TOOL, collect as collect_report
PEOPLE={'somdutta':'Somdutta','shobha':'Shobha','shivangsh':'Shivangsh'}
TOOL={'name':'get_visited_locations','description':'Read recorded named-zone visits for a household person over the entire requested time range in ONE call. Supply start and optional end as timezone-aware ISO datetimes; omit end for now. Do not split a requested range into daily calls. Default view=places returns all distinct recorded places with counts and first/last observations. Use view=intervals only when the user needs a detailed chronological timeline, including transit/unknown gaps. Available history depends on HA recorder retention; this tool imposes no seven-day limit. Zone crossings are not proof of stops.','inputSchema':{'type':'object','properties':{'person':{'type':'string','enum':['somdutta','shobha','shivangsh'],'description':'Which household member.'},'start':{'type':'string','description':'Inclusive ISO datetime with timezone offset for the beginning of the full requested range.'},'end':{'type':'string','description':'Exclusive ISO datetime with timezone offset. Omit to query through now.'},'view':{'type':'string','enum':['places','intervals'],'default':'places','description':'places lists every distinct place compactly; intervals returns the detailed timeline.'}},'required':['person','start'],'additionalProperties':False},'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}}
def get_history(args):
 if set(args)-{'person','start','end','view'}:raise ValueError('Use person, start, optional end and view for the complete requested range.')
 view=args.get('view','places')
 if view not in ('places','intervals'):raise ValueError('view must be places or intervals.')
 person=args.get('person','').strip().lower()
 if person not in PEOPLE:raise ValueError('person must be one of: '+', '.join(PEOPLE))
 entity='person.'+person
 who=PEOPLE[person]
 now=dt.datetime.now(TZ)
 if not args.get('start'):raise ValueError('start is required for the complete requested range.')
 start=dt.datetime.fromisoformat(args['start'])
 end=dt.datetime.fromisoformat(args['end']) if args.get('end') else now
 if start.tzinfo is None or end.tzinfo is None:raise ValueError('start/end must include timezone offsets.')
 start=start.astimezone(TZ);end=end.astimezone(TZ)
 if start>=end:raise ValueError('start must precede end.')
 if end>now:raise ValueError('Cannot request future history; omit end to query through now.')
 ha,auth=connection()
 query=urllib.parse.urlencode({'filter_entity_id':entity,'end_time':end.isoformat(),'significant_changes_only':'1'})
 url=ha['url'].split('/api/')[0]+'/api/history/period/'+urllib.parse.quote(start.isoformat(),safe=':+-')+'?'+query
 req=urllib.request.Request(url,headers={'Authorization':auth,'Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=5) as response:data=json.load(response)
 rows=next((g for g in data if g and g[0].get('entity_id')==entity),[])
 changes=[]
 for row in sorted(rows,key=lambda r:r.get('last_changed','')):
  stamp=dt.datetime.fromisoformat(row['last_changed']).astimezone(TZ)
  if stamp>=end:continue
  state=row['state'].strip()
  if changes and changes[-1][1]==state:continue
  changes.append((max(stamp,start),state))
 intervals=[];gaps=[]
 for idx,(stamp,state) in enumerate(changes):
  until=changes[idx+1][0] if idx+1<len(changes) else end
  item={'from':stamp.isoformat(timespec='seconds'),'to':until.isoformat(timespec='seconds'),'ongoing':idx==len(changes)-1 and end==now}
  if state in ['not_home','unknown','unavailable']:
   item['status']='away/transit' if state=='not_home' else state;gaps.append(item)
  else:
   item['location']='Home' if state=='home' else state;intervals.append(item)
 result={'person':who,'timezone':str(TZ),'requested_range':{'from':start.isoformat(timespec='seconds'),'to':end.isoformat(timespec='seconds')},'source':'Home Assistant recorder: '+entity,'as_of':end.isoformat(timespec='seconds'),'recorded_locations':intervals,'transit_or_unknown_intervals':gaps,'history_rows':len(rows),'first_record_at':rows[0].get('last_changed') if rows else None,'last_record_at':rows[-1].get('last_changed') if rows else None,'limitation':'Requested range is not a guarantee of recorder retention or tracking continuity. Recorded named-zone presence only. Zone crossings may be brief passages, not stops. Unnamed GPS stops and unrecorded visits are not identified. No fabricated addresses.'}
 if view=='places':
  places={}
  for item in intervals:
   name=item['location']
   if name not in places:places[name]={'location':name,'interval_count':0,'first_seen':item['from'],'last_seen':item['to']}
   places[name]['interval_count']+=1
   places[name]['last_seen']=item['to']
  result.pop('recorded_locations')
  result.pop('transit_or_unknown_intervals')
  result['places']=list(places.values())
  result['place_count']=len(places)
  result['transit_or_unknown_interval_count']=len(gaps)
 result['view']=view
 return result

def connection():
 ha=json.loads((Path.home()/'llm-server/ha-remote.json').read_text())
 auth=ha.get('headers',{}).get('Authorization','')
 missing=[]
 def substitute(m):
  v=os.environ.get(m[1]);
  if not v:missing.append(m[1])
  return v or ''
 auth=re.sub(r'\{env:([^}]+)\}',substitute,auth)
 if missing or not auth:raise ValueError('Home Assistant authentication environment is unavailable.')
 return ha,auth

def read_api(path):
 ha,auth=connection()
 url=ha['url'].split('/api/')[0]+path
 req=urllib.request.Request(url,headers={'Authorization':auth,'Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)

def reply(msg):
 ident=msg.get('id'); method=msg.get('method')
 if ident is None:return
 if method=='initialize': result={'protocolVersion':msg.get('params',{}).get('protocolVersion','2025-03-26'),'capabilities':{'tools':{}},'serverInfo':{'name':'ha-history','version':'1.0.0'}}
 elif method=='tools/list':result={'tools':[TOOL,CONTEXT_TOOL,STATUS_TOOL,REPORT_TOOL]}
 elif method=='tools/call':
  try:
   params=msg.get('params',{})
   name=params.get('name');args=params.get('arguments',{})
   if name==TOOL['name']:data=get_history(args)
   elif name==REPORT_TOOL['name']:data=collect_report(args,read_api)
   elif name==STATUS_TOOL['name']:data=collect_status(args,read_api)
   elif name==CONTEXT_TOOL['name']:data=collect_context(args,read_api)
   else:raise ValueError('Unknown tool')
   result={'content':[{'type':'text','text':json.dumps(data)}],'isError':False}
  except Exception as exc:
   safe=str(exc) if isinstance(exc,ValueError) else type(exc).__name__+' while reading HA history'
   result={'content':[{'type':'text','text':json.dumps({'error':safe})}],'isError':True}
 elif method=='ping':result={}
 else:
  print(json.dumps({'jsonrpc':'2.0','id':ident,'error':{'code':-32601,'message':'Method not found'}}),flush=True);return
 print(json.dumps({'jsonrpc':'2.0','id':ident,'result':result}),flush=True)
if __name__=='__main__':
 for line in sys.stdin:
  try:reply(json.loads(line))
  except (ValueError,KeyError):continue
