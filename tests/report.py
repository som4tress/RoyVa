"""Per-prompt report from proxy captures. Usage: python3 -I tests/report.py [since-stamp YYYYMMDDHHMMSS (UTC)]"""
import json, os, sys, collections
D = '/home/somdutta/RoyVa/captures'
since = sys.argv[1] if len(sys.argv) > 1 else '0'
rows = [json.loads(l) for l in open(os.path.join(D, 'index.jsonl'))]
resp = {r['id']: r for r in rows if r['type'] == 'resp'}
groups = collections.OrderedDict()
for r in rows:
    if r['type'] != 'req' or 'error' in r or r['id'][:14] < since:
        continue
    b = json.load(open(os.path.join(D, r['id'] + '.req.json')))
    users = [m for m in b['messages'] if m['role'] == 'user']
    if not users:
        continue
    c = users[0]['content']
    q = (c if isinstance(c, str) else ''.join(p.get('text', '') for p in c)).strip()
    if q.startswith('Here is the first message'):      # title-generation side call
        continue
    groups.setdefault(q[:70], []).append(r['id'])
print(f"{'prompt':50s} reqs maxtok  secs  tools(n) / sequence")
for q, ids in groups.items():
    seq, ms, mx, last = [], 0, 0, ''
    for i in ids:
        p = resp.get(i, {}); ms += p.get('ms') or 0
        mx = max(mx, (p.get('usage') or {}).get('prompt_tokens') or 0)
        seq += [c['name'].replace('home-assistant_', 'HA:').replace('homeassistant__', '') for c in p.get('tool_calls', [])]
        if p.get('content_preview'): last = p['content_preview']
    cnt = collections.Counter(seq)
    print(f"{q[:50]:50s} {len(ids):4d} {mx:6d} {ms/1000:5.0f}  {sum(cnt.values())}: {dict(cnt)}")
    print(f"     answer: {last[:230].replace(chr(10), ' ') or '(none captured)'}")
