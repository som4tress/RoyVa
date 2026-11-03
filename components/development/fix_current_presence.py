from pathlib import Path
import json,urllib.request,base64
h=Path.home();p=h/'.config/opencode/plugins/ha-mcp-routing/index.js';s=p.read_text();(h/'opencode-migration-backup/routing-before-presence-fix.js').write_text(s)
s=s.replace(" // present-tense presence: \"where is Shobha\", \"where's Shobha now\", \"is Shobha home\", \"Shobha location\"\n return PEOPLE.test(s)&&/\\b(where|where'?s|location|locate|home|away|at|in transit|zone)\\b/.test(s);", " return false;")
pos=s.index('const devices=');s=s[:pos]+"const presence=s=>PEOPLE.test(s)&&/\\b(where\\s+(?:is|are)|where'?s|current location|location|locate|home|away|zone)\\b/.test(s)&&!/\\b(yesterday|visited|visits|history|been|went|earlier|past|locations)\\b/.test(s);\n"+s[pos:]
s=s.replace(" if(history(s))return 'history';", " if(presence(s))return 'devices';\n if(history(s))return 'history';")
s=s.replace("const statusOnly=kind==='devices'&&", "const statusOnly=presence(text.toLowerCase())||kind==='devices'&&")
s=s.replace("    state.requestText=text;state.reportOnly=reportOnly;", "    state.requestText=text;state.reportOnly=reportOnly;state.presence=presence(text.toLowerCase());\n    if(state.presence)state.fastStatus=true;")
s=s.replace("    if(state.fastStatus&&!state.reportOnly)instruction+=", "    if(state.presence)instruction+='\\nThis is a CURRENT person-location request. Call get_device_status with the requested household person friendly name and domain [person]. Report that live state only; do not call visited-locations/history tools. A home/zone state is not a precise GPS address.';\n    if(state.fastStatus&&!state.reportOnly&&!state.presence)instruction+=")
p.write_text(s)
p=h/'.config/opencode/mcp/ha_device_status.py';s=p.read_text().replace("'binary_sensor','sensor']", "'binary_sensor','sensor','person','device_tracker']");p.write_text(s)
pw=(h/'llm-server/opencode.env').read_text().strip().split('=',1)[1]
req=urllib.request.Request('http://127.0.0.1:49374/api/session/ses_tg_6064019420_mvrjdeyx/interrupt',data=b'{}',headers={'Content-Type':'application/json','Authorization':'Basic '+base64.b64encode(('opencode:'+pw).encode()).decode()},method='POST')
try:r=urllib.request.urlopen(req,timeout=8);print('Pending session interrupted:',r.status)
except Exception as e:print('Interrupt:',type(e).__name__)
