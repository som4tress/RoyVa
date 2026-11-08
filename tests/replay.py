"""Replay OpenCode's captured first-step request at the model, N times per arm, to separate model randomness from
OpenCode behaviour. Talks to llama.cpp directly (no OpenCode, no Telegram).
Usage: python3 -I tests/replay.py [N=20] [arms=A,A0,B,C,D] [prompts=P1,P2,...]"""
import json, os, re, sys, time, urllib.request, collections
from concurrent.futures import ThreadPoolExecutor

R = '/home/somdutta/RoyVa'
CAP = R + '/captures'
KEY = open(os.path.expanduser('~/.local/state/llamacpp/api-key')).read().strip()
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
ARMS = (sys.argv[2] if len(sys.argv) > 2 else 'A,A0,B,C,D').split(',')
ONLY = sys.argv[3].split(',') if len(sys.argv) > 3 else None

PROMPTS = {
    'P1': ('What is the status of lights upstairs?', r'GetLiveContext|GetDateTime'),
    'P2': ('How much distance has my mustang travelled this week?', r'GetLiveContext|GetDateTime'),
    'P3': ('What is the weather forecast for the next 10 days?', r'^(websearch|webfetch)$'),
    'P4': ('What is the weather inside and outside of my house?', r'GetLiveContext|^(websearch|webfetch)$'),
    'P5': ('List the top 20 oldest unread emails from my gmail.', r'^gmail_'),
    'P6': ('Find any email that has mention of "XYZ".', r'^gmail_'),
}
ALLOW = {'websearch', 'webfetch', 'home-assistant_homeassistant__GetLiveContext', 'home-assistant_llm__GetDateTime',
         'home-assistant_media_player__search_media', 'gmail_list_labels', 'gmail_list_messages', 'gmail_read_message',
         'gmail_search_messages'}
SYS_B = ("You are RoyVa, the personal assistant for the Roy family's home. Use your tools to look things up; do not guess or "
         "invent values. If a tool returns an error or nothing, say so plainly. Keep answers short and direct.")
SYS_D = SYS_B + (" Home Assistant holds all data about the home, its devices, sensors and the family's connected vehicles "
                 "(for example the Mustang). Gmail holds the user's email. Web search and fetch answer anything else, such as "
                 "weather forecasts. Always call a tool to look something up before answering; never say you lack access or "
                 "ask the user for details until a tool has returned nothing.")
REFUSAL = re.compile(r"(don'?t|do not|cannot|can'?t|unable to|no) (have )?(any )?(access|tool|way)|not able to (access|check)", re.I)

def text(c):
    return c if isinstance(c, str) else ''.join(p.get('text', '') for p in c)

def captured(prompt):
    """Latest first-step request (system+user only, tools present) whose user text equals the prompt."""
    best = None
    for f in sorted(os.listdir(CAP)):
        if not f.endswith('.req.json'):
            continue
        try:
            b = json.load(open(os.path.join(CAP, f)))
        except Exception:
            continue
        m = b.get('messages', [])
        if len(m) == 2 and m[0]['role'] == 'system' and m[1]['role'] == 'user' and b.get('tools') \
                and text(m[1]['content']).strip() == prompt:
            best = b
    return best

def build(base, arm):
    b = json.loads(json.dumps(base))
    b['stream'] = False
    b.pop('stream_options', None)
    b['max_tokens'] = 400
    b.pop('model', None)
    if os.environ.get('REPLAY_NOCACHE') == '1':
        b['cache_prompt'] = False   # control: every request recomputes the full prompt from scratch
    if arm == 'A0':
        b.update(temperature=0, top_p=1, top_k=1, presence_penalty=0)
    if arm in ('B', 'C', 'D'):
        b['messages'][0]['content'] = SYS_D if arm == 'D' else SYS_B
    if arm in ('C', 'D'):
        b['tools'] = [t for t in b['tools'] if t['function']['name'] in ALLOW]
    return b

def call(body):
    req = urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions', json.dumps(body).encode(),
                                 {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY})
    m = json.load(urllib.request.urlopen(req, timeout=300))['choices'][0]['message']
    tcs = m.get('tool_calls') or []
    return [(t['function']['name'], t['function'].get('arguments', '')) for t in tcs], (m.get('content') or '')

rows = []
jobs = []
for pid, (q, want) in PROMPTS.items():
    if ONLY and pid not in ONLY:
        continue
    base = captured(q)
    if base is None:
        print('no captured first-step request for', pid, '- run the suite once first'); continue
    for arm in ARMS:
        for i in range(N):
            jobs.append((pid, want, arm, build(base, arm)))

def run(j):
    pid, want, arm, body = j
    try:
        calls, content = call(body)
    except Exception as e:
        return dict(pid=pid, arm=arm, err=str(e)[:80])
    first = calls[0][0] if calls else None
    return dict(pid=pid, arm=arm, first=first, sig=(first, calls[0][1][:70] if calls else None),
                ok=bool(first and re.search(want, first)), text_only=not calls,
                refusal=(not calls) and bool(REFUSAL.search(content)), content=content[:120])

t0 = time.time()
with ThreadPoolExecutor(2) as ex:
    rows = list(ex.map(run, jobs))
json.dump(rows, open(R + '/runtime/results/replay_%d.json' % int(t0), 'w'))
print('%d requests in %.0fs, errors: %d\n' % (len(rows), time.time() - t0, sum(1 for r in rows if 'err' in r)))
print('prompt arm  n  first-tool-ok  text-only  refusal  distinct-first-calls   top first call')
for pid in PROMPTS:
    for arm in ARMS:
        rs = [r for r in rows if r['pid'] == pid and r['arm'] == arm and 'err' not in r]
        if not rs:
            continue
        n = len(rs)
        sigs = collections.Counter(r['sig'] for r in rs)
        top = sigs.most_common(1)[0]
        pc = lambda k: '%3d%%' % round(sum(1 for r in rs if r[k]) / n * 100)
        print('%-4s %-3s %3d  %12s  %9s  %7s  %20d   %s x%d' % (pid, arm, n, pc('ok'), pc('text_only'), pc('refusal'),
              len(sigs), str(top[0][0]).replace('home-assistant_', 'HA:')[:34], top[1]))
    print()
