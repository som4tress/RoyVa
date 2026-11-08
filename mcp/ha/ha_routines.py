"""MCP server (stdio, newline JSON-RPC) for existing Home Assistant routines (automations, scripts, scenes).
list_routines is read-only. run_routine is a WRITE tool and can only trigger routines named in an owner-maintained allowlist file
(default: empty = nothing can run). Name matching ignores case, spaces and punctuation ("bedtime" == "Bed Time").
NOT wired into OpenCode or the gateway until the owner approves (catalog marks the tools unavailable)."""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ha_registry                                                   # noqa: E402

DOMAINS = {"automation": ("automation", "trigger"), "script": ("script", "turn_on"), "scene": ("scene", "turn_on")}
DRY_FLAG = Path(os.environ.get("ROYVA_DRY_RUN_FLAG", Path(__file__).resolve().parents[2] / "runtime" / "gateway" / "dry_run"))
ALLOWLIST = Path(os.environ.get("ROYVA_ROUTINES_ALLOWLIST", Path(__file__).resolve().parents[2] / "runtime" / "gateway" / "routines_allowlist.json"))

LIST = {"name": "list_routines",
        "description": "List the existing Home Assistant routines (automations, scripts, scenes) by name, optionally filtered by words, and whether each is allowed to be run.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "Optional words to filter by."}}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}}
RUN = {"name": "run_routine",
       "description": "Run ONE existing routine by name or entity_id (for example when the user says they are going to bed or leaving the house). Only routines the owner has allowed can run; "
                      "this changes things in the home, so say plainly what you ran. Does not create or edit routines.",
       "inputSchema": {"type": "object", "properties": {"name": {"type": "string", "description": "Routine name or entity_id."}}, "required": ["name"], "additionalProperties": False},
       "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}}


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def load_allowlist(path=None) -> set:
    path = Path(path or ALLOWLIST)
    try:
        return {norm(x) for x in json.loads(path.read_text())}
    except (OSError, ValueError):
        return set()                                                  # no file / bad file = nothing is allowed


def routines(states: list) -> list:
    out = []
    for s in states:
        d = s["entity_id"].split(".")[0]
        if d in DOMAINS:
            out.append({"entity_id": s["entity_id"], "name": s["attributes"].get("friendly_name") or s["entity_id"], "domain": d,
                        "last_triggered": s["attributes"].get("last_triggered")})
    return out


def is_allowed(r: dict, allow: set) -> bool:
    return norm(r["entity_id"]) in allow or norm(r["name"]) in allow


def resolve(query: str, rs: list) -> list:
    q = norm(query)
    exact = [r for r in rs if q in (norm(r["entity_id"]), norm(r["name"]))]
    return exact or [r for r in rs if q and q in norm(r["name"])]


def plan_run(name: str, states: list, allow: set) -> dict:
    """Pure decision: which routine would run, or why not. Never touches the network."""
    matches = resolve(name, routines(states))
    if not matches:
        return {"error": f"no routine matches '{name}'"}
    if len(matches) > 1:
        return {"error": "ambiguous", "candidates": [m["name"] for m in matches][:8]}
    r = matches[0]
    if not is_allowed(r, allow):
        return {"error": f"'{r['name']}' is not on the allowed list; ask the owner to allow it", "routine": r["name"]}
    domain, service = DOMAINS[r["domain"]]
    return {"ok": True, "routine": r["name"], "entity_id": r["entity_id"], "service": f"{domain}.{service}"}


def _base_and_token():
    ws_url, token = ha_registry._connection()
    return ws_url.replace("wss://", "https://").replace("ws://", "http://").replace("/api/websocket", ""), token


def _get(path):
    base, token = _base_and_token()
    with urllib.request.urlopen(urllib.request.Request(base + path, headers={"Authorization": f"Bearer {token}"}), timeout=20) as r:
        return json.load(r)


def _post(path, body):
    base, token = _base_and_token()
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def list_routines(args, get=_get, allow=None):
    allow = load_allowlist() if allow is None else allow
    q = norm(args.get("query", ""))
    rs = [r for r in routines(get("/api/states")) if not q or q in norm(r["name"])]
    return {"routines": [{**r, "allowed_to_run": is_allowed(r, allow)} for r in rs][:60]}


def run_routine(args, get=_get, post=_post, allow=None):
    allow = load_allowlist() if allow is None else allow
    plan = plan_run(str(args.get("name", "")), get("/api/states"), allow)
    if not plan.get("ok"):
        return plan
    domain, service = plan["service"].split(".")
    dry = os.environ.get("ROYVA_DRY_RUN") == "1" or DRY_FLAG.exists()
    status = None if dry else post(f"/api/services/{domain}/{service}", {"entity_id": plan["entity_id"]})
    return {**plan, "http_status": status, "dry_run": dry or None,
            "did": ("[DRY RUN, nothing happened] " if dry else "") + f"Ran routine '{plan['routine']}' ({plan['service']})",
            "note": "triggered; conditions inside the routine may still stop it from doing anything"}


def handle(msg):
    method, ident = msg.get("method"), msg.get("id")
    if method == "initialize":
        result = {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}},
                  "serverInfo": {"name": "ha-routines", "version": "1.0.0"}}
    elif method == "tools/list":
        result = {"tools": [LIST, RUN]}
    elif method == "tools/call":
        p = msg.get("params", {})
        try:
            fn = {"list_routines": list_routines, "run_routine": run_routine}[p.get("name")]
            result = {"content": [{"type": "text", "text": json.dumps(fn(p.get("arguments", {})))}]}
        except Exception as e:                                          # noqa: BLE001
            result = {"content": [{"type": "text", "text": json.dumps({"error": str(e)[:300]})}], "isError": True}
    elif ident is None:
        return
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "Method not found"}}), flush=True)
        return
    print(json.dumps({"jsonrpc": "2.0", "id": ident, "result": result}), flush=True)


if __name__ == "__main__":
    for line in sys.stdin:
        if line.strip():
            try:
                handle(json.loads(line))
            except Exception as e:                                      # noqa: BLE001
                print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)[:200]}}), flush=True)
