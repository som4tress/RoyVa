from pathlib import Path
import os,sys,json,subprocess,time
h=Path.home();env=dict(os.environ)
for n in ['api.env','opencode.env','ha.env']:
 for line in (h/'llm-server'/n).read_text().splitlines():k,v=line.split('=',1);env[k]=v.strip('"');os.environ[k]=v.strip('"')
sys.path.insert(0,str(h/'.config/opencode/mcp'))
from ha_history import read_api
from ha_device_status import collect
initial=collect({'name':'Den Switch','domain':['light']},read_api)['matches'];assert len(initial)==1 and initial[0]['state'] in ['on','off'];start=initial[0]['state'];target='off' if start=='on' else 'on';print('Den initial:',start,flush=True)
def run(action,label):
 t=time.monotonic();r=subprocess.run([str(h/'.opencode/bin/opencode'),'run','--server','http://127.0.0.1:49374','--format','json','--auto','--agent','telegram','--model','openrouter/deepseek/deepseek-v4.1-flash-1017',f'Turn the den light {action}.'],cwd=h,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=100)
 (h/f'llm-server/ha-write-{label}.jsonl').write_text(r.stdout);(h/f'llm-server/ha-write-{label}.log').write_text(r.stderr)
 print(label,'exit',r.returncode,'seconds',round(time.monotonic()-t,1),flush=True)
 for l in r.stdout.splitlines():
  d=json.loads(l);p=d.get('part',{})
  if d.get('type')=='tool_use':print('tool',p.get('tool'),'input',p.get('state',{}).get('input'),'status',p.get('state',{}).get('status'),flush=True)
  if d.get('type')=='text':print('reply',p.get('text','')[:250],flush=True)
try:
 run(target,'test');state=collect({'name':'Den Switch','domain':['light']},read_api)['matches'][0]['state'];print('Verified Den state:',state,flush=True)
finally:
 current=collect({'name':'Den Switch','domain':['light']},read_api)['matches'][0]['state']
 if current!=start:run(start,'restore')
 print('Restored to initial state:',collect({'name':'Den Switch','domain':['light']},read_api)['matches'][0]['state']==start,flush=True)
