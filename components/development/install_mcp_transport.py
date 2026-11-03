from pathlib import Path
import json
h=Path.home();p=h/'.config/opencode/opencode.json';d=json.loads(p.read_text());remote=d['mcp']['servers']['home-assistant'];assert remote['type']=='remote'
p2=h/'llm-server/ha-remote.json';p2.write_text(json.dumps(remote));p2.chmod(0o600)
d['mcp']['servers']['home-assistant']={'type':'local','command':['/usr/bin/python3','/home/somdutta/.config/opencode/mcp/ha_mcp_transport.py'],'codemode':False};p.write_text(json.dumps(d,indent=2)+'\n')
p=h/'.config/opencode/mcp/ha_history.py';s=p.read_text().replace(" ha=cfg['mcp']['servers']['home-assistant']"," ha=cfg['mcp']['servers']['home-assistant']\n if ha.get('type')=='local':ha=json.loads((Path.home()/'llm-server/ha-remote.json').read_text())");p.write_text(s)
p=h/'.config/opencode/plugins/ha-mcp-routing/index.js';s=p.read_text();s='\n'.join(l for l in s.split('\n') if "event:'tool-api-probe'" not in l);s=s.replace("state.fastStatus?{type:'function',function:{name:'ha-history_get_device_status'}}:","state.fastStatus?'required':");p.write_text(s)
print('HA MCP now uses a local transport adapter; the same remote tools and authentication remain in use.')
