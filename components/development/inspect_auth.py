import json,pathlib,sqlite3
h=pathlib.Path.home();d=json.loads((h/'.config/opencode/opencode.json').read_text());m=d['mcp']['servers']['home-assistant'];print('HA header forms',[(k,'env-reference' if '{env:' in str(v) else 'literal',len(str(v))) for k,v in m['headers'].items()]);print('API URL',m['url']);print('history auth sources:')
s=(h/'.config/opencode/mcp/ha_history.py').read_text();print('\n'.join(l for l in s.splitlines() if any(a in l for a in ['getenv','environ','activate','TOKEN =','URL ='])))
