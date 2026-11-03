import json,time,urllib.request,sys
from pathlib import Path
root=Path('/home/somdutta/llm-server/direct-qwen-20261103')
env=dict(l.split('=',1) for l in Path('/home/somdutta/llm-server/api.env').read_text().splitlines() if '=' in l and not l.startswith('#'))
key=env['VLLM_API_KEY'].strip('"\'')
old=json.loads(Path('/home/somdutta/.local/share/opencode/cloud-context/payloads/3f2b4f57-0354-4eb7-983d-7c9de63ab07f/modified.json').read_text())
tools=[t for t in old['tools'] if t['function']['name'] in ('websearch','webfetch')]
prompt='What does the weather look like till 21 Nov in Milpitas, California?'
messages=[{'role':'system','content':'Today is 2026-11-03. Timezone: America/Los_Angeles. You are a helpful assistant.'},{'role':'user','content':prompt}]
cases=[('bare-current',False,False,{}),('bare-recommended',False,False,{'temperature':.7,'top_p':.8,'top_k':20,'presence_penalty':1.5}),('tools-current',True,False,{}),('tools-recommended',True,False,{'temperature':.7,'top_p':.8,'top_k':20,'presence_penalty':1.5}),('tools-low-temperature',True,False,{'temperature':.2,'top_p':.8,'top_k':20,'presence_penalty':0}),('tools-thinking',True,True,{'temperature':1.,'top_p':.95,'top_k':20,'presence_penalty':1.5})]
if len(sys.argv)>1:
 payload=json.loads(Path(sys.argv[1]).read_text());cases=[('continuation',True,payload.get('chat_template_kwargs',{}).get('enable_thinking',False),{})]
results=[]
for name,with_tools,thinking,params in cases:
 if len(sys.argv)==1:
  payload={'model':'qwen36-agent','messages':messages,'stream':False,'seed':17,'max_tokens':2048 if thinking else 512,'chat_template_kwargs':{'enable_thinking':thinking},**params}
  if with_tools:payload['tools']=tools
 start=time.monotonic()
 print(json.dumps({'event':'start','name':name}),flush=True)
 try:
  req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
  with urllib.request.urlopen(req,timeout=150) as res: data=json.load(res)
  row={'name':name,'seconds':round(time.monotonic()-start,2),'usage':data.get('usage'),'choice':data.get('choices',[{}])[0]}
 except Exception as e:row={'name':name,'error':str(e),'seconds':round(time.monotonic()-start,2)}
 results.append(row)
 (root/(name+'.request.json')).write_text(json.dumps(payload,indent=2))
 (root/(name+'.response.json')).write_text(json.dumps(row,indent=2))
 if len(sys.argv)==1:(root/'results.json').write_text(json.dumps(results,indent=2))
 print(json.dumps(row),flush=True)
