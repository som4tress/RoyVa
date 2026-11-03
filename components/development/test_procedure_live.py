from pathlib import Path
import os,subprocess,json,time,ast
h=Path.home();env=dict(os.environ)
for n in ['api.env','opencode.env','ha.env']:
 for line in (h/'llm-server'/n).read_text().splitlines():k,v=line.split('=',1);env[k]=v.strip('"')
task='Create /home/somdutta/OpenCodeRunner/procedure-memory-smoke.py with a square(x) function that returns x*x. Use the write tool; do not execute it.'
for label in ['create','recall']:
 t=time.monotonic();r=subprocess.run([str(h/'.opencode/bin/opencode'),'run','--server','http://127.0.0.1:49374','--format','json','--auto','--agent','telegram','--model','openrouter/deepseek/deepseek-v4.1-flash-1017',task],cwd=h/'OpenCodeRunner',env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=90)
 (h/f'llm-server/procedure-memory-{label}.jsonl').write_text(r.stdout)
 print(label,'exit',r.returncode,'seconds',round(time.monotonic()-t,1),flush=True)
 if r.returncode:print(r.stderr[-300:]);break
p=h/'OpenCodeRunner/procedure-memory-smoke.py';assert p.exists();ast.parse(p.read_text());d=json.loads((h/'.local/share/opencode/procedures/index.json').read_text());refs=[e for e in d['entries'] if any(f['path']==str(p) for f in e['files'])];print('Generated file parsed and automatically indexed:',bool(refs))
