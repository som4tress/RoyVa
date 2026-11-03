from pathlib import Path
import os,sys,subprocess,json,time,urllib.request
h=Path.home();env=dict(os.environ)
for n in ['api.env','opencode.env','ha.env']:
 for line in (h/'llm-server'/n).read_text().splitlines():k,v=line.split('=',1);env[k]=v.strip('"');os.environ[k]=v.strip('"')
sys.path.insert(0,str(h/'.config/opencode/mcp'))
from ha_history import read_api
from ha_device_status import collect

def state():
 rows=collect({'name':'Den Switch','domain':['light']},read_api)['matches'];assert len(rows)==1 and rows[0]['state'] in ['on','off'];return rows[0]['state']
def count():
 s=urllib.request.urlopen('http://127.0.0.1:8000/metrics',timeout=5).read().decode();return sum(float(l.split()[-1]) for l in s.splitlines() if l.startswith('vllm:request_success_total{'))
results=[]
def ask(query,label):
 before=count();t=time.monotonic();r=subprocess.run([str(h/'.opencode/bin/opencode'),'run','--server','http://127.0.0.1:49374','--format','json','--auto','--agent','telegram','--model','openrouter/deepseek/deepseek-v4.1-flash-1017',query],cwd=h,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=75)
 (h/f'llm-server/template-den-{label}.jsonl').write_text(r.stdout)
 text=' '.join(json.loads(l).get('part',{}).get('text','').strip() for l in r.stdout.splitlines() if json.loads(l).get('type')=='text')
 row={'label':label,'seconds':round(time.monotonic()-t,2),'LLM_calls':count()-before,'reply':text,'actual_Den_state':state()};results.append(row);print(json.dumps(row),flush=True);assert r.returncode==0;return row
initial=state();target='on' if initial=='off' else 'off';print('Initial Den state: '+initial,flush=True)
try:
 ask('Is Den Switch on?','learn-status')
 ask(f'Turn den light {target}.','learn-write');assert state()==target
 fresh=ask('Is Den Switch on?','fresh-status');assert fresh['LLM_calls']==0 and target in fresh['reply']
 ask(f'Turn den light {initial}.','learn-restore');assert state()==initial
 direct=ask(f'Turn den light {target}.','direct-write');assert direct['LLM_calls']==0 and state()==target
 direct=ask(f'Turn den light {initial}.','direct-restore');assert direct['LLM_calls']==0 and state()==initial
finally:
 if state()!=initial:ask(f'Turn den light {initial}.','final-restore')
 print('Original state restored: '+str(state()==initial),flush=True)
 (h/'llm-server/template-den-benchmark.json').write_text(json.dumps(results,indent=2))
