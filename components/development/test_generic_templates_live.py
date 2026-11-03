from pathlib import Path
import os,subprocess,json,time,urllib.request
h=Path.home();env=dict(os.environ)
for n in ['api.env','opencode.env','ha.env']:
 for line in (h/'llm-server'/n).read_text().splitlines():k,v=line.split('=',1);env[k]=v.strip('"')
def metrics():return json.load(urllib.request.urlopen('http://127.0.0.1:8011/metrics',timeout=5))
query="What is this computer's kernel version? Use uname -r."
results=[]
for index in [1,2]:
 before=metrics();start=time.monotonic();r=subprocess.run([str(h/'.opencode/bin/opencode'),'run','--server','http://127.0.0.1:49374','--format','json','--auto','--agent','telegram','--model','openrouter/deepseek/deepseek-v4.1-flash-1017',query],cwd=h,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=90)
 after=metrics();(h/f'llm-server/template-host-{index}.jsonl').write_text(r.stdout)
 texts=[];tools=[]
 for l in r.stdout.splitlines():
  d=json.loads(l);p=d.get('part',{})
  if d.get('type')=='text':texts.append(p.get('text','').strip())
  if d.get('type')=='tool_use':tools.append(p.get('tool'))
 row={'run':index,'exit':r.returncode,'seconds':round(time.monotonic()-start,2),'upstream_model_calls':after['upstream']-before['upstream'],'template_hits':after['templateHits']-before['templateHits'],'reply':' '.join(texts),'tools':tools};print(json.dumps(row),flush=True);results.append(row)
 if r.returncode:print(r.stderr[-500:],flush=True);break
(h/'llm-server/template-host-benchmark.json').write_text(json.dumps(results,indent=2))
