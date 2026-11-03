from pathlib import Path
import os,subprocess,json,time,urllib.request,re
h=Path.home();env=dict(os.environ)
for n in ['api.env','opencode.env','ha.env']:
 for line in (h/'llm-server'/n).read_text().splitlines():k,v=line.split('=',1);env[k]=v.strip('"')
def metrics():
 text=urllib.request.urlopen('http://127.0.0.1:8000/metrics',timeout=5).read().decode()
 return {name:sum(float(l.split()[-1]) for l in text.splitlines() if l.startswith('vllm:'+name+'{')) for name in ['request_success_total','generation_tokens_total']}
query=os.environ.get('TEMPLATE_TEST_QUERY','Is the kitchen light on?')
for index in [1,2]:
 before=metrics();start=time.monotonic()
 r=subprocess.run([str(h/'.opencode/bin/opencode'),'run','--server','http://127.0.0.1:49374','--format','json','--auto','--agent','telegram','--model','openrouter/deepseek/deepseek-v4.1-flash-1017',query],cwd=h,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=90)
 elapsed=round(time.monotonic()-start,2);after=metrics();(h/f'llm-server/template-live-{index}.jsonl').write_text(r.stdout)
 replies=[];tools=[]
 for l in r.stdout.splitlines():
  try:
   d=json.loads(l);p=d.get('part',{})
   if d.get('type')=='text':replies.append(p.get('text','').strip())
   if d.get('type')=='tool_use':tools.append(p.get('tool'))
  except ValueError:pass
 print(json.dumps({'run':index,'exit':r.returncode,'seconds':elapsed,'vllm_requests':after['request_success_total']-before['request_success_total'],'generated_tokens':after['generation_tokens_total']-before['generation_tokens_total'],'reply':' '.join(replies)[:250],'tools':tools}),flush=True)
 if r.returncode:print(r.stderr[-400:],flush=True)
