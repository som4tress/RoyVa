import json,pathlib
h=pathlib.Path.home()
for label in ['create','recall']:
 tools=[]
 for line in (h/f'llm-server/procedure-memory-{label}.jsonl').read_text().splitlines():
  d=json.loads(line)
  if d.get('type')=='tool_use':tools.append(d.get('part',{}).get('tool'))
 print(label,'tools:',tools)
p=h/'.local/share/opencode/procedures/index.json';d=json.loads(p.read_text());print('Indexed procedures:',len(d['entries']),'private mode:',oct(p.stat().st_mode&0o777));print('Report indexed:',any(e['tool']=='ha-history_get_device_status_report' for e in d['entries']))
