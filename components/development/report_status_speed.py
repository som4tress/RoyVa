import json,pathlib
h=pathlib.Path.home()
for label in ['before','after']:
 p=h/f'llm-server/ha-speed-{label}.jsonl'
 print(label)
 for l in p.read_text().splitlines():
  d=json.loads(l);p=d.get('part',{})
  if d.get('type')=='tool_use':
   st=p.get('state',{});print('tool',p.get('tool'),'input',st.get('input'),'status',st.get('status'),'output_chars',len(str(st.get('output',''))))
  if d.get('type')=='step_finish':print('tokens',p.get('tokens'))
