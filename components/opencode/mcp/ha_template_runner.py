"""Bounded execution/certification for learned Home Assistant procedures.
No shell execution or arbitrary URLs. Writes use the existing HA MCP endpoint.
"""
import json,sys,re,datetime as dt,urllib.request,time
from pathlib import Path
from zoneinfo import ZoneInfo
from ha_history import read_api,connection,get_history,PEOPLE
from ha_device_status import collect as status
from ha_status_report import collect as report
TZ=ZoneInfo('America/Los_Angeles')
STATUS='ha-history_get_device_status'
REPORT='ha-history_get_device_status_report'
HISTORY='ha-history_get_visited_locations'
ON='home-assistant_intent__HassTurnOn';OFF='home-assistant_intent__HassTurnOff'
SUPPORTED={STATUS,REPORT,HISTORY,ON,OFF}
COMMON=set('turn switch set please on off light lights fan fans device devices room the a an is are what status state show me of my home house in to bedroom currently'.split())
def words(s):return set(re.findall(r'[\w]+',str(s).casefold()))
def standalone(q,write=False):
 if not isinstance(q,str) or not 2<len(q)<600:return False
 s=q.casefold();s=re.sub(r'\bmy (home|house)\b','the home',s)
 if re.search(r'password|bearer|api.?key|secret|\btoken\b|\b(route|deepseek|glm|qwen|model)\b|[;`{}]',s):return False
 if re.search(r'\b(?:and|then|also)\s+(?:then\s+)?(?:turn|switch|set|run|show|share|check|send|announce|broadcast|play|summarize)\b',s):return False
 if re.search(r'\b(it|them|those|these|this|that|again|same|previous|last|instead|if|unless|until|whenever|after|before)\b',s):return False
 if write:
  return bool(re.match(r'^(?:please\s+)?(?:turn|switch|set)\b',s)) and not re.search(r'\b(and|also|then|when|tomorrow|tonight|later|briefly|temporarily|restore|revert|minutes?|seconds?|hours?|schedule|except|never|not|don\W?t|every|all|everything|my|our)\b|[;\n`{}]|\b\d{1,2}:\d{2}\b',s)
 return not re.search(r'\b(turn|toggle|enable|disable|activate|delete|remove|run|execute|why|explain|compare|cause|caused|not|except)\b',s)
def grounded(q,name):
 query=words(q)-COMMON;target=words(name)-COMMON
 if query&target:return True
 # Existing household person names can ground common shortened friendly names.
 names=list(PEOPLE.values())
 for person in names:
  p=person.casefold()
  if p not in query or len(p)<4:continue
  prefix=p[:4]
  if sum(n.casefold().startswith(prefix) for n in names)==1 and any(t.startswith(prefix) for t in target):return True
 return False
def checked_args(tool,args,q):
 if tool in [STATUS,REPORT,HISTORY]:q=re.sub(r'[.!?;]?\s*(?:do not change anything|make no changes|read[ -]only)[.!?]*$','',q,flags=re.I).strip()
 if tool not in SUPPORTED or not isinstance(args,dict):raise ValueError('Unsupported procedure.')
 if tool in [STATUS,REPORT]:
  allowed={'name','domain'} if tool==STATUS else {'domains','name','state','limit','include_diagnostics','area','floor'}
  if set(args)-allowed:raise ValueError('Unsupported arguments.')
  if not standalone(q):raise ValueError('Request depends on context or analysis.')
  if tool==STATUS and re.search(r'\b(and|also|both|plus)\b|[,;&]',q,re.I):raise ValueError('Multi-target status requires the agent or a report.')
  if tool==REPORT:
   if args.get('name') and not grounded(q,args['name']):raise ValueError('Report name filter is not grounded.')
   for scope in ['area','floor']:
    if args.get(scope) and (not isinstance(args[scope],str) or not grounded(q,args[scope])):raise ValueError('Report scope is not grounded.')
   if not any(args.get(k) for k in ['name','area','floor']) and not re.search(r'\b(all|every|devices|entities|home|house)\b',q,re.I):raise ValueError('Unfiltered report is not explicitly requested.')
   if args.get('state') and not re.search(r'\b'+re.escape(str(args['state']))+r'\b',q,re.I):raise ValueError('Report state filter is not requested.')
   if args.get('include_diagnostics') and not re.search(r'\b(sensors?|diagnostics?|entities|trackers?|people|person)\b',q,re.I):raise ValueError('Diagnostic scope is not requested.')
   if not re.search(r'\b(devices|entities|everything)\b',q,re.I) and re.search(r'\blights?\b',q,re.I) and not args.get('name'):
    if not args.get('domains') or any(d not in ['light','switch'] for d in args['domains']):raise ValueError('Light-only report scope is too broad.')
  if tool==STATUS and re.search(r'\b(brightness|bright|temperature|degrees|percentage|speed|battery|power|watt|who|how|when|since|yesterday|ago|historical|history|past|week|month|hours|minutes)\b',q,re.I):raise ValueError('Status request needs interpretation beyond the saved formatter.')
  if tool==STATUS and not grounded(q,args.get('name','')):raise ValueError('Named target is not grounded in the request.')
  return dict(args)
 if tool==HISTORY:
  if re.search(r'how long|how many|duration|distance|miles|kilomet|total|\bstops?\b|stopped',q,re.I):raise ValueError('History request requires additional analysis.')
  named=[p for p in PEOPLE.values() if re.search(r'\b'+re.escape(p)+r'\b',q,re.I)]
  if len(named)!=1 or (re.search(r'\btoday\b',q,re.I) and re.search(r'\byesterday\b',q,re.I)) or len(re.findall(r'\b\d{4}-\d{2}-\d{2}\b',q))>1:raise ValueError('History needs exactly one explicit person and day.')
  safe_query=re.sub(r'\b(?:last|past)\s+(?:(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+)?hours?\b','rolling window',q,flags=re.I) if args.get('hours') is not None else q
  if not standalone(safe_query) or set(args)-{'person','date','hours'} or args.get('person') not in PEOPLE:raise ValueError('Invalid history procedure.')
  if not grounded(q,PEOPLE[args['person']]):raise ValueError('Person is not grounded.')
  result={'person':args['person']}
  if args.get('hours') is not None:
   hours=args['hours'];numbers={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12}
   match=re.search(r'\b(?:last|past)\s+(?:(\d+|'+ '|'.join(numbers)+r')\s+)?hours?\b',q,re.I)
   if not match or type(hours) is not int or not 1<=hours<=168 or args.get('date'):raise ValueError('Rolling hour scope is not explicit.')
   value=(match[1] or 'one').lower();requested=int(value) if value.isdigit() else numbers[value]
   if requested!=hours:raise ValueError('Rolling hour scope mismatch.')
   return {'person':args['person'],'hours':hours}
  today=dt.datetime.now(TZ).date()
  if re.search(r'\btoday\b',q,re.I):return result
  if re.search(r'\byesterday\b',q,re.I):result['date']=(today-dt.timedelta(days=1)).isoformat();return result
  date=args.get('date')
  if date:
   if date not in q:raise ValueError('Only explicit ISO dates or relative today/yesterday are reusable.')
   dt.date.fromisoformat(date);result['date']=date
  return result
 if not standalone(q,True) or set(args)-{'name','domain'}:raise ValueError('Write must name one device without broad selectors.')
 desired='on' if tool==ON else 'off'
 if len(re.findall(r'\b(?:on|off)\b',q,re.I))!=1 or not re.search(r'\b'+desired+r'\b',q,re.I):raise ValueError('Write polarity mismatch.')
 name=args.get('name');domain=args.get('domain',[])
 if not isinstance(name,str) or not name.strip() or not grounded(q,name):raise ValueError('Write target is not grounded.')
 if isinstance(domain,str):domain=[domain]
 if not isinstance(domain,list) or any(d not in ['light','switch','fan'] for d in domain):raise ValueError('Only single-device light/switch/fan on/off is reusable.')
 return {'name':name,'domain':domain} if domain else {'name':name}
def target_for(args):
 name=args['name'].strip().casefold();domains=args.get('domain',[])
 rows=[r for r in read_api('/api/states') if r.get('entity_id','').split('.')[0] in ['light','switch','fan'] and (not domains or r['entity_id'].split('.')[0] in domains) and str(r.get('attributes',{}).get('friendly_name','')).strip().casefold()==name]
 if len(rows)!=1:raise ValueError('Device no longer resolves uniquely.')
 row=rows[0];identity=row['entity_id']+' '+str(row.get('attributes',{}).get('friendly_name',''))
 if re.search(r'linux|server|nuc|\bpc\b|computer|workstation|\bbox\b',identity,re.I):raise ValueError('Computer/server power is excluded from direct execution.')
 if row.get('state') not in ['on','off']:raise ValueError('Device state is unavailable or unsupported.')
 return row

def verified_state(args,eid,desired):
 deadline=time.monotonic()+2.0
 while True:
  row=target_for(args)
  if row['entity_id']!=eid:raise ValueError('Target identity changed.')
  if row['state']==desired:return row
  if time.monotonic()>=deadline:raise ValueError('Desired state not verified.')
  time.sleep(0.15)

def mcp_call(tool,args):
 remote,auth=connection();headers={'Authorization':auth,'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
 def post(message):
  req=urllib.request.Request(remote['url'],headers=headers,data=json.dumps(message).encode(),method='POST')
  with urllib.request.urlopen(req,timeout=5) as r:
   sid=r.headers.get('Mcp-Session-Id')
   if sid:headers['Mcp-Session-Id']=sid
   raw=r.read().decode();kind=r.headers.get('Content-Type','')
  if not raw.strip():return {}
  if 'text/event-stream' in kind:
   for block in raw.replace('\r\n','\n').split('\n\n'):
    data='\n'.join(l[5:].strip() for l in block.splitlines() if l.startswith('data:'))
    if data:
     item=json.loads(data)
     if item.get('id')==message.get('id'):return item
   raise ValueError('No MCP response.')
  return json.loads(raw)
 hello=post({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'opencode-verified-procedure','version':'1'}}})
 if hello.get('error'):raise ValueError('MCP initialization failed.')
 headers['MCP-Protocol-Version']=hello.get('result',{}).get('protocolVersion','2025-03-26')
 post({'jsonrpc':'2.0','method':'notifications/initialized'})
 result=post({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':tool.removeprefix('home-assistant_'),'arguments':args}})
 if result.get('error') or result.get('result',{}).get('isError'):raise ValueError('HA MCP action reported an error.')
 return result.get('result',{})

def certify(req):
 tool=req.get('tool');q=req.get('query','');data=req.get('data')
 if not isinstance(data,dict) or data.get('error') or data.get('isError'):raise ValueError('No successful structured result.')
 raw=req.get('args',{})
 if tool in [ON,OFF]:
  successes=data.get('data',{}).get('success',[])
  if data.get('data',{}).get('failed') or len(successes)!=1:raise ValueError('Write result does not prove exactly one successful entity.')
  eid=successes[0].get('id');rows=[r for r in read_api('/api/states') if r.get('entity_id')==eid]
  if len(rows)!=1:raise ValueError('Verified entity no longer exists.')
  raw={'name':rows[0].get('attributes',{}).get('friendly_name',''),'domain':[eid.split('.')[0]]}
 args=checked_args(tool,raw,q)
 recipe={'tool':tool,'args':args,'kind':'read','query':q}
 if tool==STATUS:
  if data.get('read_only') is not True or not data.get('matches') or data.get('count')!=len(data['matches']):raise ValueError('Status result is empty/invalid.')
  recipe['expected_entities']=sorted(m['entity_id'] for m in data['matches'])
 elif tool==REPORT:
  if data.get('kind')!='ha_status_report' or data.get('read_only') is not True or data.get('version')!=1:raise ValueError('Invalid report result.')
  for scope in ['area','floor']:
   if str(data.get('filters',{}).get(scope) or '').strip().casefold()!=str(args.get(scope) or '').strip().casefold():raise ValueError('Report result scope differs from certified arguments.')
  if sorted(data.get('domains',[]))!=sorted(args.get('domains',data.get('domains',[]))):raise ValueError('Report result domains differ from certified arguments.')
 elif tool==HISTORY:
  if data.get('person')!=PEOPLE[args['person']] or data.get('logbook_error'):raise ValueError('History person/result mismatch.')
  expected=args.get('date') or dt.datetime.now(TZ).date().isoformat()
  if args.get('hours') is not None and data.get('requested_range',{}).get('hours')!=args['hours']:raise ValueError('History time window mismatch.')
  if data.get('date')!=expected:raise ValueError('History date mismatch.')
  if re.search(r'\b(today|yesterday)\b',q,re.I):
   recipe['datePolicy']='yesterday' if re.search(r'\byesterday\b',q,re.I) else 'today'
   recipe['args'].pop('date',None)
 else:
  row=target_for(args);desired='on' if tool==ON else 'off'
  successes=data.get('data',{}).get('success',[]);failures=data.get('data',{}).get('failed',[])
  if failures or len(successes)!=1 or successes[0].get('id')!=row['entity_id']:raise ValueError('Write was not verified on exactly the intended entity.')
  row=verified_state(args,row['entity_id'],desired)
  recipe.update(kind='write',expected_entities=[row['entity_id']],desired=desired)
  # Use the actual uniquely resolved friendly name and domain, not model traces.
  recipe['args']={'name':row['attributes']['friendly_name'],'domain':[row['entity_id'].split('.')[0]]}
 return {'ok':True,'recipe':recipe}
def execute(req):
 recipe=req.get('recipe',{});q=req.get('query','');tool=recipe.get('tool');args=checked_args(tool,recipe.get('args',{}),q)
 if tool==STATUS:
  data=status(args,read_api)
  if not data.get('matches') or sorted(m['entity_id'] for m in data['matches'])!=recipe.get('expected_entities'):raise ValueError('Status targets changed.')
  return {'ok':True,'data':data,'tool':tool}
 if tool==REPORT:return {'ok':True,'data':report(args,read_api),'tool':tool}
 if tool==HISTORY:return {'ok':True,'data':get_history(args),'tool':tool}
 row=target_for(args)
 if [row['entity_id']]!=recipe.get('expected_entities'):raise ValueError('Write target changed.')
 desired='on' if tool==ON else 'off'
 if row['state']==desired:return {'ok':True,'tool':tool,'data':{'name':row['attributes']['friendly_name'],'state':desired,'already':True}}
 try:
  mcp_call(tool,args)
  after=verified_state(args,row['entity_id'],desired)
  return {'ok':True,'tool':tool,'data':{'name':after['attributes']['friendly_name'],'state':desired,'already':False}}
 except Exception:
  # Never hand an uncertain write back to the LLM for an automatic retry.
  try:
   after=target_for(args)
   if after['entity_id']==row['entity_id'] and after['state']==desired:return {'ok':True,'tool':tool,'data':{'name':after['attributes']['friendly_name'],'state':desired,'already':False}}
  except Exception:pass
  return {'ok':False,'write_uncertain':True,'message':'The device action could not be verified. Please check its state before retrying.'}
if __name__=='__main__':
 try:
  req=json.load(sys.stdin)
  result=certify(req) if req.get('operation')=='certify' else execute(req) if req.get('operation')=='execute' else {'ok':False,'message':'Unknown operation.'}
 except Exception as exc:result={'ok':False,'message':str(exc) if isinstance(exc,ValueError) else type(exc).__name__}
 print(json.dumps(result))
