from pathlib import Path
import json
h=Path.home();p=h/'.config/opencode/opencode.json';d=json.loads(p.read_text());v=d['providers']['vllm'];a=d['providers']['evo-agent'];v['package']=a['package'];v['settings']={**a['settings'],'baseURL':'http://127.0.0.1:8011/local/v1'}
for key,m in v['models'].items():
 m['name']='EVO 35B Agent (legacy session alias)';m['limit']['context']=131072;m['capabilities']['input']=['text'];m['body']['chat_template_kwargs']['enable_thinking']=True
p.write_text(json.dumps(d,indent=2)+'\n')
p=h/'.config/opencode/lib/media-deadline-proxy.mjs';t=p.read_text().replace("const ha=req.headers['x-request-kind']==='ha';","const incoming=JSON.parse(Buffer.concat(chunks).toString());\n  const ha=req.headers['x-request-kind']==='ha'||(!cloud&&['qwen38-27b','qwen35-9b'].includes(incoming.model));");p.write_text(t)
print('Legacy local model aliases mapped to EVO for existing sessions.')
