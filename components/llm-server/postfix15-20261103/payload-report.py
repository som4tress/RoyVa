from pathlib import Path
import json,csv,difflib,zipfile,os,datetime
r=Path(__file__).parent;root=Path('/home/somdutta/.local/share/opencode/cloud-context/payloads');runs=json.loads((r/'results.json').read_text());mapping={x['sessionId']:x for x in runs};out=r/'payload-review';out.mkdir(exist_ok=True,mode=0o700)
audit=[json.loads(l) for l in (root.parent/'audit.jsonl').read_text().splitlines() if l.strip()]
records=[json.loads(l) for l in (root/'index.jsonl').read_text().splitlines()];records=[x for x in records if x.get('session') in mapping];records.sort(key=lambda x:(mapping[x['session']]['id'],x['at']));rows=[];counts={};files=[]
for d in records:
 t=mapping[d['session']];counts[t['id']]=counts.get(t['id'],0)+1;step=counts[t['id']];p=root/d['id'];u={}
 if (p/'response-usage.json').exists():u=json.loads((p/'response-usage.json').read_text())
 usage=u.get('usage',{});prefix=f"{t['id']:02d}-{step:02d}-{d['id'][:8]}";target=out/prefix;target.mkdir(exist_ok=True,mode=0o700)
 for name in ['original.json','modified.json','comparison.json','response-usage.json']:
  if (p/name).exists():(target/name).write_bytes((p/name).read_bytes());files.append(target/name)
 diff=''.join(difflib.unified_diff((p/'original.json').read_text().splitlines(True),(p/'modified.json').read_text().splitlines(True),fromfile='original.json',tofile='modified.json')) or 'UNCHANGED: original and modified payloads are identical.\n'
 (target/'diff.patch').write_text(diff);files.append(target/'diff.patch')
 stamp=datetime.datetime.fromisoformat(d['at'].replace('Z','+00:00')).timestamp()*1000
 matches=[x for x in audit if x.get('event')=='request' and x.get('session')==d.get('session') and x.get('beforeBytes')==d['originalBytes'] and x.get('afterBytes')==d['modifiedBytes'] and abs(x.get('at',0)-stamp)<1000]
 prep=min(matches,key=lambda x:abs(x['at']-stamp)).get('elapsedMs') if matches else None
 row={'preprocessing_ms':prep,'workload_id':t['id'],'workload':t['name'],'step':step,'request_id':d['id'],'unchanged':d['unchanged'],'original_bytes':d['originalBytes'],'modified_bytes':d['modifiedBytes'],'saved_bytes':d['savedBytes'],'saved_pct':round(d['savedPercent'],2),'actual_prompt_tokens':usage.get('prompt_tokens'),'actual_cached_tokens':usage.get('prompt_tokens_details',{}).get('cached_tokens'),'actual_completion_tokens':usage.get('completion_tokens'),'actual_reasoning_tokens':usage.get('completion_tokens_details',{}).get('reasoning_tokens'),'provider_reported_usd':usage.get('cost'),'provider':u.get('provider'),'http_status':u.get('status'),'folder':prefix};rows.append(row)
with (out/'index.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=rows[0] if rows else []);w.writeheader();w.writerows(rows)
lines=['# Every outgoing DeepSeek payload — post-fix fifteen-test benchmark','', 'Original and modified bodies below are credential-redacted review copies. HTTP authorization headers are excluded. Byte counts measure the serialized live JSON, before display redaction/pretty printing. Original token counts are not guessed; returned prompt tokens are the actual modified-request usage. Unchanged means no compression was applied. Every tool schema, current instruction and tool-call argument is preserved.','', '| Workload / request | Original bytes | Modified bytes | Saved | Prep ms | Review |','|---|---:|---:|---:|---:|---|']
for z in rows:
 f=out/z['folder'];lines.append(f"| {z['workload_id']}.{z['step']} {z['workload']} | {z['original_bytes']:,} | {z['modified_bytes']:,} | {z['saved_pct']:.1f}% | {z['preprocessing_ms']} | [Original]({f}/original.json) · [Modified]({f}/modified.json) · [Diff]({f}/diff.patch) |")
(out/'index.md').write_text('\n'.join(lines)+'\n');files.extend([out/'index.csv',out/'index.md'])
with zipfile.ZipFile(r/'payload-review.zip','w',zipfile.ZIP_DEFLATED) as z:
 for f in files:z.write(f,f.relative_to(out))
 z.writestr('README.md',(out/'index.md').read_text().replace(str(out)+'/',''))
for f in files:os.chmod(f,0o600)
os.chmod(r/'payload-review.zip',0o600)
(r/'payload-summary.json').write_text(json.dumps({'requests':len(rows),'changed_requests':sum(not x['unchanged'] for x in rows),'original_bytes':sum(x['original_bytes'] for x in rows),'modified_bytes':sum(x['modified_bytes'] for x in rows),'saved_bytes':sum(x['saved_bytes'] for x in rows),'provider_reported_cost':sum(x['provider_reported_usd'] or 0 for x in rows)},indent=2));print((r/'payload-summary.json').read_text())
