"""Write usage_backfill.json: token totals for the LOCAL models (llama.cpp 'evo-agent', earlier 'vllm') from OpenCode's history,
for the period before the footer's own counting began. The bridge merges it once at startup.
Usage: python3 -I scripts/make_usage_backfill.py [usage_totals.json]   (reads the OpenCode DB read-only)"""
import json, os, sqlite3, sys, datetime
state = os.environ.get("XDG_STATE_HOME", "/home/somdutta/RoyVa/runtime/state")
totals_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(state, "usage_totals.json")
db = os.environ.get("OPENCODE_DB", os.path.expanduser("~/.local/share/opencode/opencode.db"))
LOCAL = {"evo-agent", "vllm"}
since = json.load(open(totals_file))["since"]
cut = datetime.datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp() * 1000
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
t = dict(input=0, cached=0, output=0, reasoning=0, passes=0, runs=0)
first = None
sessions = set()
for sid, d, ts in c.execute("select session_id, data, time_created from session_message where type='assistant'"):
    j = json.loads(d); k = j.get("tokens")
    if not k or ts >= cut or (j.get("model") or {}).get("providerID") not in LOCAL:
        continue
    cache = (k.get("cache") or {}).get("read", 0)
    t["input"] += k.get("input", 0) + cache; t["cached"] += cache
    t["output"] += k.get("output", 0); t["reasoning"] += k.get("reasoning", 0); t["passes"] += 1
    sessions.add(sid); first = ts if first is None else min(first, ts)
t["runs"] = len(sessions)
out = {"since": datetime.datetime.fromtimestamp(first / 1000, datetime.timezone.utc).isoformat() if first else since, "totals": t}
json.dump(out, open(os.path.join(os.path.dirname(totals_file), "usage_backfill.json"), "w"))
print(out)
