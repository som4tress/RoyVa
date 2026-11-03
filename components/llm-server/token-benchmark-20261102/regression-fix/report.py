from pathlib import Path
import json,csv,sys
r=Path('/home/somdutta/llm-server/token-benchmark-20261102');old={x['id']:x for x in json.loads((r/'input-only.json').read_text())};new=json.loads((r/((sys.argv[1] if len(sys.argv)>1 else 'regression-v3')+'.json')).read_text());oldrows=list(csv.DictReader((r/'payload-review/index.csv').open()));events=[json.loads(l) for l in Path('/home/somdutta/.local/share/opencode/cloud-context/audit.jsonl').read_text().splitlines() if l.strip()];rows=[]
for t in new:
 b=old[t['id']];e=[x for x in events if x.get('session')==t['sessionId'] and x.get('event')=='request' and x.get('version')==t.get('codeVersion',4 if len(sys.argv)>1 and sys.argv[1]=='regression-v4' else 3)];row={'id':t['id'],'workload':t['name'],'old_seconds':b['seconds'],'fixed_seconds':t['seconds'],'old_prep_seconds':round(sum(float(x['preprocessing_ms'] or 0) for x in oldrows if int(x['workload_id'])==t['id'])/1000,3),'fixed_prep_seconds':round(sum(x['elapsedMs'] for x in e)/1000,3),'fixed_qwen_attempts':sum(x['attempts'] for x in e),'fixed_negative_hits':sum(x['negativeHits'] for x in e),'fixed_changed_requests':sum(x['changed']>0 for x in e),'fixed_saved_bytes':sum(x['beforeBytes']-x['afterBytes'] for x in e),'old_cost':b['usage']['cost'],'fixed_cost':t['usage']['cost'],'old_calls':b['usage']['requests'],'fixed_calls':t['usage']['requests'],'ok':t['ok']};rows.append(row)
(r/'regression-fix/comparison.json').write_text(json.dumps(rows,indent=2));
if rows:
 with (r/'regression-fix/comparison.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
print(json.dumps(rows,indent=2))
