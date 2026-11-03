from pathlib import Path
import json,hashlib,datetime
r=Path(__file__).parent
baseline=json.loads((r.parent/'postfix15-20261103/results.json').read_text())
latest={x['id']:x for x in json.loads((r/'results.json').read_text())}
p=r.parent/'clean-context-retest-20261103/results.json'
if p.exists():latest.update({x['id']:x for x in json.loads(p.read_text())})
p=r.parent/'lean-instructions-20261103/results.json'
if p.exists():latest.update({x['id']:x for x in json.loads(p.read_text())})
lines=['# Focused context-cleanup benchmark','', 'Normal prompts via the production Telegram handler and real private-chat delivery. Local-first routing, fresh diagnostic sessions. Output includes provider reasoning. Cloud input includes cached input. Cache rates and live source data vary; these are observed comparisons, not controlled causal estimates. The 60-second goal is soft, never a hard abort.','', '| Workload | Before → latest seconds | Cloud input before → latest | Cloud output before → latest | Cost before → latest |','|---|---:|---:|---:|---:|']
for i,x in latest.items():
 b=next((z for z in baseline if z['id']==i),None)
 if not b:b={'seconds':13.594,'usage':dict(fresh=0,cached=0,output=0,reasoning=0,cost=0)}
 u,v=b['usage'],x['usage'];lines.append(f"| {i}. {x['name']} | {b['seconds']:.1f} → {x['seconds']:.1f} | {u['fresh']+u['cached']:,} → {v['fresh']+v['cached']:,} | {u['output']+u['reasoning']:,} → {v['output']+v['reasoning']:,} | ${u['cost']:.5f} → ${v['cost']:.5f} |")
lines+=['','Correctness is reviewed separately from completion and timing. The first cleanup inventory reply incorrectly said six active devices while listing five. The first incident reply incorrectly treated discovery as proof of reachability. Those replies are not accepted as quality passes. The DST count and first/last timestamps are checked against the known full-data oracle.','', 'Changes: exact JSON whitespace reduction; bounded large tool evidence with local full-source recovery; identical-result deduplication tied to exact tool arguments; smaller advisory recall hints; skip irrelevant semantic-recall work; batched calculation guidance; registry-based diagnostic filtering and structured state filters. Required instructions, schemas, tool IDs/arguments and provider reasoning are retained. No task-name-specific routing.','', 'Expensive second local-model compression passes remain disabled. The cheap cloud gate is enabled globally; large-result excerpts require a read/shell recovery tool. Source files and tool capabilities remain available.']
(r/'REPORT.md').write_text('\n'.join(lines)+'\n')
paths=[Path.home()/'.config/opencode'/p for p in ['lib/evidence-window.mjs','lib/cloud-context-optimizer.mjs','lib/task-learning.mjs','lib/procedure-memory.mjs','lib/user-scope.mjs','lib/ha-reports.mjs','mcp/ha_status_report.py','plugins/procedure-memory/index.js','instructions/formatting.md','cloud-context.json']]
(r/'source-manifest.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},indent=2))
print(r/'REPORT.md')
