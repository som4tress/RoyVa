from pathlib import Path
import subprocess,os,json,time
h=Path.home();env=dict(os.environ)
for n in ['api.env','opencode.env','ha.env']:
 for line in (h/'llm-server'/n).read_text().splitlines():
  k,v=line.split('=',1);env[k]=v.strip('"')
args=[str(h/'.opencode/bin/opencode'),'run','--server','http://127.0.0.1:49374','--format','json','--auto','--agent','telegram','--model','openrouter/deepseek/deepseek-v4.1-flash-1017','Which recorded locations did Somdutta visit today?']
t=time.monotonic()
try:
 r=subprocess.run(args,cwd=h,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=100);(h/'llm-server/ha-speed-history.jsonl').write_text(r.stdout);(h/'llm-server/ha-speed-history.log').write_text(r.stderr)
 print('Read-only OpenCode HA test:',r.returncode,'elapsed',round(time.monotonic()-t,1))
 for l in r.stdout.splitlines():
  try:
   d=json.loads(l)
   if d.get('type')=='text':print(d.get('part',{}).get('text','')[:350])
  except ValueError:pass
except subprocess.TimeoutExpired: print('Read-only HA test timed out')



