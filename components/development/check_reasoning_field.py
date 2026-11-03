import json
from pathlib import Path
import urllib.request
root = Path.home() / 'llm-server'
key = (root / 'api.env').read_text().strip().split('=',1)[1]
body = {'model':'qwen36-agent','messages':[{'role':'user','content':'What is 2+2?'}],'max_tokens':8,'stream':True,'chat_template_kwargs':{'enable_thinking':True}}
req = urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=60) as response:
    for line in response:
        if line.startswith(b'data: {'):
            d=json.loads(line[6:])
            for c in d.get('choices',[]):
                delta=c.get('delta',{})
                if any(delta.get(k) for k in ('reasoning','reasoning_content','reasoning_text')):
                    print('Reasoning fields:',[k for k in delta if delta.get(k)])
                    raise SystemExit(0)
