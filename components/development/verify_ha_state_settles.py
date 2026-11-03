from pathlib import Path
p=Path.home()/'.config/opencode/mcp/ha_template_runner.py';s=p.read_text().replace('import json,sys,re,os,datetime as dt,urllib.request,difflib','import json,sys,re,os,datetime as dt,urllib.request,difflib,time')
anchor='\ndef mcp_call(tool,args):'
insert='''
def verified_state(args,eid,desired):
 deadline=time.monotonic()+2.0
 while True:
  row=target_for(args)
  if row['entity_id']!=eid:raise ValueError('Target identity changed.')
  if row['state']==desired:return row
  if time.monotonic()>=deadline:raise ValueError('Desired state not verified.')
  time.sleep(0.15)
'''
assert anchor in s;s=s.replace(anchor,insert+anchor)
s=s.replace("  if failures or len(successes)!=1 or successes[0].get('id')!=row['entity_id'] or row['state']!=desired:raise ValueError('Write was not verified on exactly the intended entity.')", "  if failures or len(successes)!=1 or successes[0].get('id')!=row['entity_id']:raise ValueError('Write was not verified on exactly the intended entity.')\n  row=verified_state(args,row['entity_id'],desired)")
s=s.replace("  after=target_for(args)\n  if after['entity_id']!=row['entity_id'] or after['state']!=desired:raise ValueError('Desired state not verified.')", "  after=verified_state(args,row['entity_id'],desired)")
p.write_text(s)
