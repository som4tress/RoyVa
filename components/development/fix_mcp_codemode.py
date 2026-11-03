from pathlib import Path
import json
h=Path.home();p=h/'.config/opencode/opencode.json';d=json.loads(p.read_text());m=d['mcp']['servers']['home-assistant'];print('Remote MCP codemode before:',m.get('codemode','default'));m['codemode']=False;p.write_text(json.dumps(d,indent=2)+'\n')
p=h/'.config/opencode/plugins/ha-mcp-routing/index.js';s=p.read_text();s='\n'.join(l for l in s.split('\n') if "event:'fast-wire-tools'" not in l);p.write_text(s)
