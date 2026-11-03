import json,os,time,subprocess,urllib.request,pathlib,statistics
r=pathlib.Path(__file__).parent;config=r.parent/'servers.json';env=dict(os.environ,XDG_RUNTIME_DIR='/run/user/1000',DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1000/bus')
secret={}
for line in (r.parent/'api.env').read_text().splitlines():
 if '=' in line:
  k,v=line.split('=',1);secret[k.strip()]=v.strip().strip('\"\'')
headers={'Content-Type':'application/json','Authorization':'Bearer '+secret['VLLM_API_KEY']}
body=json.loads((r/'request.json').read_text());body['max_tokens']=2048;payload=json.dumps(body).encode();results=[]
def configure(n):
 d=json.loads(config.read_text());d['servers']['agent']['batch_tokens']=n;config.write_text(json.dumps(d,indent=2)+'\n')
def restart(n):
 print(json.dumps({'event':'restart','batch':n}),flush=True)
 p=subprocess.run(['systemctl','--user','restart','evo-vllm-agent'],env=env,capture_output=True,text=True,timeout=600)
 if p.returncode:raise RuntimeError('Agent restart failed; restoring baseline')
 print(json.dumps({'event':'ready','batch':n}),flush=True)
def measure(n):
 start=time.monotonic();first=None;usage={};calls={};content='';finish=None
 req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=payload,headers=headers)
 with urllib.request.urlopen(req,timeout=240) as response:
  for line in response:
   if not line.startswith(b'data: '):continue
   data=line[6:].strip()
   if data==b'[DONE]':break
   d=json.loads(data)
   if d.get('usage'):usage=d['usage']
   for choice in d.get('choices',[]):
    delta=choice.get('delta',{})
    if delta.get('content') or delta.get('tool_calls'):
     if first is None:first=time.monotonic()-start
    content+=delta.get('content') or ''
    for call in delta.get('tool_calls',[]):
     i=call['index'];entry=calls.setdefault(i,{'name':'','arguments':''});f=call.get('function',{});entry['name']+=f.get('name','');entry['arguments']+=f.get('arguments','')
    finish=choice.get('finish_reason') or finish
 elapsed=time.monotonic()-start;valid=bool(calls)
 for call in calls.values():
  try:json.loads(call['arguments'])
  except:valid=False
 result={'batch':n,'ttft_s':round(first,3) if first else None,'total_s':round(elapsed,3),'usage':usage,'finish_reason':finish,'valid_tool_json':valid,'tool_names':[c['name'] for c in calls.values()]}
 (r/f'response-{n}.json').write_text(json.dumps({'result':result,'calls':calls,'content':content},indent=2));return result
try:
 for n in [2048,4096,8192,16384]:
  configure(n);
  if n!=2048:restart(n)
  result=measure(n);results.append(result);(r/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps({'event':'result',**result}),flush=True)
 valid=[x for x in results if x['valid_tool_json'] and x['finish_reason']!='length']
 base=next((x for x in valid if x['batch']==2048),None);best=min(valid,key=lambda x:x['ttft_s']) if valid else None
 chosen=best['batch'] if base and best['ttft_s']<base['ttft_s']*.9 and best['total_s']<=base['total_s']*1.1 else 2048
 configure(chosen)
 if chosen!=16384:restart(chosen)
 (r/'decision.json').write_text(json.dumps({'chosen':chosen,'note':'Single cold-cache replay per setting; no claim of statistically reliable ranking. Require >=10% lower TTFT and no >10% total regression to change baseline.'},indent=2));print(json.dumps({'event':'finished','chosen':chosen}),flush=True)
except Exception as e:
 print(json.dumps({'event':'failed','error':type(e).__name__}),flush=True);configure(2048);restart(2048);raise
