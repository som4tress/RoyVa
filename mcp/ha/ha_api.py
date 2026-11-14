"""MCP server (stdio, newline JSON-RPC): a generic door to Home Assistant's own API, for things no purpose-built tool covers
(assign a device to an area, create or edit an automation or scene, rename an entity, read any registry or config).
Two tools, so the permission layer can treat them differently:
  ha_read   - only calls that cannot change anything (WebSocket list/get-style commands, REST GET). Anything else is refused with a pointer to ha_write.
  ha_write  - everything else. Registered as an always-ask tool: the owner sees the exact call and approves it before it runs.
Secrets are never exposed (auth commands are refused). Honors the dry-run flag like ha_routines.py."""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ha_registry                                                   # noqa: E402
import ha_ws                                                         # noqa: E402

DRY_FLAG = Path(os.environ.get("ROYVA_DRY_RUN_FLAG", Path(__file__).resolve().parents[2] / "runtime" / "gateway" / "dry_run"))
MAX_OUT = 20000
READ_LAST = {"list", "get", "list_for_display", "get_states", "get_config", "get_services", "get_panels", "get_themes", "search", "render_template",
             "history_during_period", "statistics_during_period", "get_events", "ping"}
REFUSED = re.compile(r"(^|/)(auth|auth_provider)(/|$)|token|password|subscribe", re.I)        # secrets and streaming: never, in either tool


def norm(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def protected_names() -> list:
    return [norm(x) for x in os.environ.get("ROYVA_PROTECTED_DEVICES", "").split(",") if norm(x)]


def is_read_ws(t: str) -> bool:
    last = t.rsplit("/", 1)[-1]
    return last in READ_LAST or last.startswith("get_") or last.startswith("list_")


def check_read(kind: str, target: str, method: str = "GET", params: dict = None):
    """None if allowed, else the reason. Pure."""
    if params and ({"type", "id"} & set(params)):
        return "params may not set 'type' or 'id'; the command is given by the target"
    if REFUSED.search(target):
        return "that call can expose secrets or streams and is never allowed"
    if kind == "ws":
        return None if is_read_ws(target) else "that command can change things; use ha_write (it asks the owner first)"
    if kind == "rest":
        if method.upper() != "GET":
            return "only GET is allowed here; use ha_write for anything else"
        return None if target.startswith("/api/") else "REST paths must start with /api/"
    if kind == "config":
        return None
    return "kind must be 'ws', 'rest' or 'config'"


MAX_CALL = 100_000


CONFIG_ITEM = re.compile(r"^/api/config/[a-z_]+/config/([^/?#]+)$")


def _stored_id_ok(kind: str, target: str, params: dict) -> bool:
    """A saved config object carries its own id. Sending it back unchanged (REST save to /api/config/<kind>/config/<same id>) is fine; any other id is not."""
    m = CONFIG_ITEM.match(target) if kind == "rest" else None
    return bool(m) and params.get("id") == m.group(1)


def check_write(kind: str, target: str, method: str, params: dict):
    forbidden = {"type", "id"} & set(params or {})
    if forbidden == {"id"} and _stored_id_ok(kind, target, params):
        forbidden = set()
    if forbidden:
        return "params may not set 'type' or 'id'; the command is given by the target"
    if REFUSED.search(target):
        return "that call can expose secrets or streams and is never allowed"
    if kind == "rest" and not target.startswith("/api/"):
        return "REST paths must start with /api/"
    if kind not in ("ws", "rest"):
        return "kind must be 'ws' or 'rest'"
    blob = json.dumps(params or {}) + " " + target
    if len(blob) > MAX_CALL:     # a long call is fine: the approval card attaches it as a file. This is only a sanity ceiling.
        return f"call is larger than {MAX_CALL} characters; split it into smaller steps"
    hits = [n for n in protected_names() if n in norm(blob)]
    if hits and len(set(re.findall(r"\b[a-z_]+\.[a-z0-9_]+\b", blob.lower()))) > 1:
        return "a protected device is part of a multi-target change; change it on its own, with explicit approval"
    return None


def _auth():
    ws_url, token = ha_registry._connection()
    return ws_url, token, ws_url.replace("wss://", "https://").replace("ws://", "http://").replace("/api/websocket", "")


def _rest(method, path, body=None):
    _, token, base = _auth()
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method=method.upper(),
                                 headers={"Authorization": f"Bearer {token}", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
            return {"http_status": r.status, "body": _maybe_json(raw)}
    except urllib.error.HTTPError as e:
        return {"http_status": e.code, "body": e.read().decode("utf-8", "replace")[:500]}


def _maybe_json(raw: str):
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _ws(t, params):
    url, token, _ = _auth()
    out = ha_ws.call(url, token, [{**(params or {}), "id": 1, "type": t}], timeout=15)
    return out.get(1)


def _cap(result):
    text = json.dumps(result, separators=(",", ":"))
    if len(text) <= MAX_OUT:
        return result
    return {"truncated": True, "hint": "the result is too big: ask again with contains (text to match), fields (keys to keep) and limit", "first_chars": text[:MAX_OUT]}


def shape(result, contains=None, fields=None, limit=50):
    """Narrow a list result on the server so a big registry never has to travel whole: keep items whose JSON contains the text,
    keep only the named keys, return at most `limit`. Anything that is not a list is returned unchanged."""
    if not isinstance(result, list):
        return result
    items = result
    if contains:
        needles = [str(c).lower() for c in (contains if isinstance(contains, list) else [contains])]
        items = [i for i in items if all(n in json.dumps(i).lower() for n in needles)]
    total = len(items)
    if fields:
        keep = [str(f) for f in fields]
        items = [{k: i.get(k) for k in keep if k in i} if isinstance(i, dict) else i for i in items]
    try:
        limit = max(1, min(int(limit or 50), 500))
    except (TypeError, ValueError):
        limit = 50
    items = items[:limit]
    while len(items) > 1 and len(json.dumps(items, separators=(",", ":"))) > MAX_OUT - 500:        # fit the cap by showing fewer, and say so
        items = items[:len(items) // 2]
    out = {"matched": total, "shown": len(items), "items": items}
    if len(items) < total:
        out["hint"] = "more matched than shown: narrow with contains, or keep fewer fields"
    return out


def _target(args):
    kind = args.get("kind", "")
    t = args.get("type") if kind == "ws" else args.get("path")
    return kind, str(t or ""), str(args.get("method") or "GET").upper(), dict(args.get("params") or {})


CONFIG_DOMAINS = ("automation", "script", "scene")


def find_config(domain, name, rest=_rest):
    """Home Assistant has no list endpoint for automation/script/scene configs and the config path needs an id the model cannot guess.
    Resolve it here: match entity states by name, take the stored id, read the saved config. Several matches are returned as a short list to choose from."""
    if domain not in CONFIG_DOMAINS:
        return {"error": f"domain must be one of {', '.join(CONFIG_DOMAINS)}"}
    states = rest("GET", "/api/states")
    body = states.get("body")
    if not isinstance(body, list):
        return {"error": "could not read entity states", "detail": states}
    words = [norm(w) for w in re.split(r"\s+", str(name).strip()) if norm(w)]      # every word must appear, in any order, in the name or entity id
    hits, everything = [], []
    for st in body:
        eid = st.get("entity_id", "")
        if not eid.startswith(domain + "."):
            continue
        attrs = st.get("attributes") or {}
        item = {"entity_id": eid, "name": attrs.get("friendly_name"), "id": attrs.get("id") or eid.split(".", 1)[1], "state": st.get("state")}
        everything.append(item)
        hay = norm(attrs.get("friendly_name", "")) + norm(eid)
        if all(w in hay for w in words):
            hits.append(item)
    if not hits:      # show every name so the model picks one itself instead of guessing more paths
        return {"error": f"no {domain} matches '{name}'", "all_names": [i["name"] or i["entity_id"] for i in everything][:200],
                "hint": "pick the closest name from all_names and call again with it. If none fits, stop and ask the owner which one they mean; do not look anywhere else."}
    if len(hits) > 1:
        return {"matches": hits[:20], "hint": "several matched: call again with a more exact name"}
    hit = hits[0]
    cfg = rest("GET", f"/api/config/{domain}/config/{hit['id']}")
    return _cap({**hit, "config_path": f"/api/config/{domain}/config/{hit['id']}", "read": cfg})


def ha_read(args, ws=_ws, rest=_rest):
    kind, target, method, params = _target(args)
    if kind == "config":
        return find_config(str(args.get("domain") or ""), str(args.get("name") or ""), rest)
    bad = check_read(kind, target, method)
    if bad:
        return {"error": bad}
    for k in ("contains", "fields", "limit"):      # models often put these inside params; they are our options, not Home Assistant fields
        if k in params and args.get(k) is None:
            args = {**args, k: params[k]}
        params.pop(k, None)
    f = {k: args.get(k) for k in ("contains", "fields", "limit")}
    if kind == "ws":
        return _cap({"result": shape(ws(target, params), **f)})
    out = rest("GET", target)
    if isinstance(out.get("body"), list):
        out = {**out, "body": shape(out["body"], **f)}
    return _cap(out)


def ha_write(args, ws=_ws, rest=_rest):
    kind, target, method, params = _target(args)
    if kind == "rest" and method == "GET":
        method = "POST"
    bad = check_write(kind, target, method, params)
    if bad:
        return {"error": bad}
    call = {"kind": kind, "target": target, "method": method if kind == "rest" else None, "params": params}
    if os.environ.get("ROYVA_DRY_RUN") == "1" or DRY_FLAG.exists():
        return {"dry_run": True, "did": f"[DRY RUN, nothing happened] {json.dumps(call)}"}
    res = {"result": ws(target, params)} if kind == "ws" else rest(method, target, params or None)
    return _cap({"done": call, **res})


READ = {"name": "ha_read",
        "description": "Read anything from Home Assistant's own API that no other tool exposes: registries (areas, devices, entities, floors, labels), "
                       "automation/script/scene config, services, history. Registries are big: always narrow list results with contains (e.g. a device name), fields and limit. kind 'ws' with type (e.g. config/device_registry/list) or kind 'rest' with path (e.g. /api/config/automation/config/<id>). "
                       "To read an automation, script or scene config by name use kind 'config' with domain and name (the lookup of its id is done for you; HA has no list endpoint for these). "
                       "Cannot change anything.",
        "inputSchema": {"type": "object", "properties": {"kind": {"type": "string", "enum": ["ws", "rest", "config"]},
                                                         "domain": {"type": "string", "enum": list(CONFIG_DOMAINS), "description": "kind config: automation, script or scene."},
                                                         "name": {"type": "string", "description": "kind config: part of the item's name, e.g. 'ford update'."},
                                                         "type": {"type": "string", "description": "WebSocket command type (kind ws)."},
                                                         "path": {"type": "string", "description": "REST path starting with /api/ (kind rest)."},
                                                         "params": {"type": "object", "description": "Extra command fields (ws) or query-free options."},
                                                         "contains": {"description": "For list results (registries, states): keep only items whose data contains this text (or all of these texts), case-insensitive. Use it, big lists are cut off.",
                                                                      "oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                                                         "fields": {"type": "array", "items": {"type": "string"}, "description": "For list results: keep only these keys of each item (e.g. id, name, area_id)."},
                                                         "limit": {"type": "integer", "description": "For list results: at most this many items (default 50)."}},
                        "required": ["kind"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}}
WRITE = {"name": "ha_write",
         "description": "Change something through Home Assistant's own API: assign a device to an area (config/device_registry/update with device_id and area_id), "
                        "create or edit an automation (rest POST /api/config/automation/config/<id>), rename an entity, call a service. The owner approves the exact call first; "
                        "look up ids with ha_read before calling, and read the result back afterwards to verify. A save REPLACES the whole stored config, so send the complete config with your change in it (a long one is fine: the owner gets it as an attached file with a list of the changes). If a call is refused, do not try another route and never look for tokens or credentials: stop and tell the owner what is blocked.",
         "inputSchema": {"type": "object", "properties": {"kind": {"type": "string", "enum": ["ws", "rest"]},
                                                          "type": {"type": "string", "description": "WebSocket command type (kind ws)."},
                                                          "path": {"type": "string", "description": "REST path starting with /api/ (kind rest)."},
                                                          "method": {"type": "string", "enum": ["POST", "PUT", "DELETE"], "description": "REST method (kind rest), default POST."},
                                                          "params": {"type": "object", "description": "Command fields (ws) or JSON body (rest)."}},
                         "required": ["kind"], "additionalProperties": False},
         "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False}}


def handle(msg):
    method, ident = msg.get("method"), msg.get("id")
    if method == "initialize":
        result = {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}},
                  "serverInfo": {"name": "ha-api", "version": "1.0.0"}}
    elif method == "tools/list":
        result = {"tools": [READ, WRITE]}
    elif method == "tools/call":
        p = msg.get("params", {})
        try:
            fn = {"ha_read": ha_read, "ha_write": ha_write}[p.get("name")]
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
