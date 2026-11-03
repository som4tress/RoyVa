import json,pathlib,csv,sqlite3,sys
r=pathlib.Path('/home/somdutta/llm-server/token-benchmark-20261102');reportdir=r/'ordered-v5'
b=json.loads((r/'baseline.json').read_text());a=json.loads((r/((sys.argv[1] if len(sys.argv)>1 else 'optimized')+'.json')).read_text());rows=[]
c=sqlite3.connect('file:/home/somdutta/.local/share/opencode/opencode.db?mode=ro',uri=True)
for x,y in zip(b,a):
 row={'id':x['id'],'workload':x['name']}
 for phase,z in [('before',x),('after',y)]:
  u=z['usage'];total=u['fresh']+u['cached'];out=u['output']+u['reasoning'];tools=[]
  for(v,)in c.execute('select data from session_message where session_id=?',[z['sessionId']]):
   tools.extend(t['name'] for t in json.loads(v).get('content',[]) if t.get('type')=='tool')
  row.update({phase+'_input':total,phase+'_fresh':u['fresh'],phase+'_cached':u['cached'],phase+'_cache_pct':100*u['cached']/max(1,total),phase+'_output':out,phase+'_visible_output':u['output'],phase+'_reasoning':u['reasoning'],phase+'_reported_usd':u['cost'],phase+'_seconds':z['seconds'],phase+'_requests':u['requests'],phase+'_tool_calls':len(tools),phase+'_tools':','.join(sorted(set(tools))),phase+'_transport_ok':z['ok']})
 row.update(saved_input=row['before_input']-row['after_input'],saved_output=row['before_output']-row['after_output'],saved_reported_usd=row['before_reported_usd']-row['after_reported_usd'])
 rows.append(row)
with (reportdir/'comparison.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
(reportdir/'comparison.json').write_text(json.dumps(rows,indent=2))
(reportdir/'summary.json').write_text(json.dumps({'completed_pairs':len(rows),'before_cost':sum(x['before_reported_usd'] for x in rows),'after_cost':sum(x['after_reported_usd'] for x in rows),'before_input':sum(x['before_input'] for x in rows),'after_input':sum(x['after_input'] for x in rows),'before_output':sum(x['before_output'] for x in rows),'after_output':sum(x['after_output'] for x in rows),'before_cached':sum(x['before_cached'] for x in rows),'after_cached':sum(x['after_cached'] for x in rows),'before_seconds':sum(x['before_seconds'] for x in rows),'after_seconds':sum(x['after_seconds'] for x in rows)},indent=2))
print(json.dumps({'completed_pairs':len(rows),'before_cost':sum(x['before_reported_usd'] for x in rows),'after_cost':sum(x['after_reported_usd'] for x in rows),'saved_input':sum(x['saved_input'] for x in rows),'saved_output':sum(x['saved_output'] for x in rows),'before_seconds':sum(x['before_seconds'] for x in rows),'after_seconds':sum(x['after_seconds'] for x in rows)},indent=2))
