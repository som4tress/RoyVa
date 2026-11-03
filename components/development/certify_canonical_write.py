from pathlib import Path
h=Path.home();p=h/'.config/opencode/mcp/ha_template_runner.py';s=p.read_text()
old=" tool=req.get('tool');q=req.get('query','');args=checked_args(tool,req.get('args',{}),q);data=req.get('data')\n if not isinstance(data,dict) or data.get('error') or data.get('isError'):raise ValueError('No successful structured result.')"
new=""" tool=req.get('tool');q=req.get('query','');data=req.get('data')
 if not isinstance(data,dict) or data.get('error') or data.get('isError'):raise ValueError('No successful structured result.')
 raw=req.get('args',{})
 if tool in [ON,OFF]:
  successes=data.get('data',{}).get('success',[])
  if data.get('data',{}).get('failed') or len(successes)!=1:raise ValueError('Write result does not prove exactly one successful entity.')
  eid=successes[0].get('id');rows=[r for r in read_api('/api/states') if r.get('entity_id')==eid]
  if len(rows)!=1:raise ValueError('Verified entity no longer exists.')
  raw={'name':rows[0].get('attributes',{}).get('friendly_name',''),'domain':[eid.split('.')[0]]}
 args=checked_args(tool,raw,q)"""
assert old in s;s=s.replace(old,new);p.write_text(s)
p=h/'.config/opencode/lib/execution-templates.mjs';s=p.read_text().replace(" const proof=await run(candidate);if(!proof.ok||!proof.recipe)return null;", " const proof=await run(candidate);if(!proof.ok||!proof.recipe){audit({event:'template-not-certified',key:sha(queryKey(candidate.query)),tool:candidate.tool,reason:proof.message||'No proof'},path);return null;}")
p.write_text(s)
