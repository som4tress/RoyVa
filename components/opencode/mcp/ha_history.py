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
TOOL={'name':'get_visited_locations','description':'Read recorded visited locations for a household person (Somdutta, Shobha, Shivangsh) on a local calendar date or rolling last N hours. Pass hours=N for rolling windows; do not combine hours with date. Use for "all locations Shobha visited today" or "where did Shivangsh go yesterday". Returns chronological named-zone intervals, including Home, plus transit gaps. This is history, not current location.','inputSchema':{'type':'object','properties':{'person':{'type':'string','enum':['somdutta','shobha','shivangsh'],'description':'Which household member.'},'date':{'type':'string','description':'Local date YYYY-MM-DD; omit for today. Mutually exclusive with hours.'},'hours':{'type':'integer','minimum':1,'maximum':168,'description':'Rolling last N hours, e.g. 1 for the last hour. Mutually exclusive with date.'}},'required':['person'],'additionalProperties':False},'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}}
def get_history(args):
 person=args.get('person','').strip().lower()
 if person not in PEOPLE:raise ValueError('person must be one of: '+', '.join(PEOPLE))
 entity='person.'+person
 who=PEOPLE[person]
 now=dt.datetime.now(TZ)
 day=dt.date.fromisoformat(args.get('date') or now.date().isoformat())
 if day>now.date():raise ValueError('Cannot request future history.')
 hours=args.get('hours')
 if hours is not None:
  if type(hours) is not int or not 1<=hours<=168 or args.get('date'):raise ValueError('hours must be 1..168 and cannot be combined with date.')
  start=(now.astimezone(dt.timezone.utc)-dt.timedelta(hours=hours)).astimezone(TZ);end=now
 else:start=dt.datetime.combine(day,dt.time(),TZ);end=min(start+dt.timedelta(days=1),now)
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
  item={'from':stamp.isoformat(timespec='seconds'),'to':until.isoformat(timespec='seconds'),'ongoing':idx==len(changes)-1 and day==now.date()}
  if state in ['not_home','unknown','unavailable']:
   item['status']='away/transit' if state=='not_home' else state;gaps.append(item)
  else:
   item['location']='Home' if state=='home' else state;intervals.append(item)
 return {'person':who,'date':day.isoformat(),'timezone':str(TZ),'requested_range':{'from':start.isoformat(timespec='seconds'),'to':end.isoformat(timespec='seconds'),'hours':hours},'source':'Home Assistant recorder: '+entity,'as_of':end.isoformat(timespec='seconds'),'recorded_locations':intervals,'transit_or_unknown_intervals':gaps,'history_rows':len(rows),'limitation':'Recorded named-zone presence only. Zone crossings may be brief passages, not stops. Unnamed GPS stops and unrecorded visits are not identified. No fabricated addresses.'}
def connection():
 cfg=json.loads((Path.home()/'.config/opencode/opencode.json').read_text())
 ha=cfg['mcp']['servers']['home-assistant']
 if ha.get('type')=='local':ha=json.loads((Path.home()/'llm-server/ha-remote.json').read_text())
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
