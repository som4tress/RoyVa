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


def check_read(kind: str, target: str, method: str = "GET"):
    """None if allowed, else the reason. Pure."""
    if REFUSED.search(target):
        return "that call can expose secrets or streams and is never allowed"
    if kind == "ws":
        return None if is_read_ws(target) else "that command can change things; use ha_write (it asks the owner first)"
    if kind == "rest":
        if method.upper() != "GET":
            return "only GET is allowed here; use ha_write for anything else"
        return None if target.startswith("/api/") else "REST paths must start with /api/"
    return "kind must be 'ws' or 'rest'"


def check_write(kind: str, target: str, method: str, params: dict):
    if REFUSED.search(target):
        return "that call can expose secrets or streams and is never allowed"
    if kind == "rest" and not target.startswith("/api/"):
        return "REST paths must start with /api/"
    if kind not in ("ws", "rest"):
        return "kind must be 'ws' or 'rest'"
    blob = json.dumps(params or {}) + " " + target
    if len(blob) > 3000:
        return "call is too long for the owner to review in full; split it into smaller steps"
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
    out = ha_ws.call(url, token, [{"id": 1, "type": t, **(params or {})}], timeout=15)
    return out.get(1)


def _cap(result):
    text = json.dumps(result)
    return result if len(text) <= MAX_OUT else {"truncated": True, "first_chars": text[:MAX_OUT]}


def _target(args):
    kind = args.get("kind", "")
    t = args.get("type") if kind == "ws" else args.get("path")
    return kind, str(t or ""), str(args.get("method") or "GET").upper(), dict(args.get("params") or {})


def ha_read(args, ws=_ws, rest=_rest):
    kind, target, method, params = _target(args)
    bad = check_read(kind, target, method)
    if bad:
        return {"error": bad}
    return _cap({"result": ws(target, params)} if kind == "ws" else rest("GET", target))


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
                       "automation/script/scene config, services, history. kind 'ws' with type (e.g. config/device_registry/list) or kind 'rest' with path (e.g. /api/config/automation/config/<id>). "
                       "Cannot change anything.",
        "inputSchema": {"type": "object", "properties": {"kind": {"type": "string", "enum": ["ws", "rest"]},
                                                         "type": {"type": "string", "description": "WebSocket command type (kind ws)."},
                                                         "path": {"type": "string", "description": "REST path starting with /api/ (kind rest)."},
                                                         "params": {"type": "object", "description": "Extra command fields (ws) or query-free options."}},
                        "required": ["kind"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}}
WRITE = {"name": "ha_write",
         "description": "Change something through Home Assistant's own API: assign a device to an area (config/device_registry/update with device_id and area_id), "
                        "create or edit an automation (rest POST /api/config/automation/config/<id>), rename an entity, call a service. The owner approves the exact call first; "
                        "look up ids with ha_read before calling, and read the result back afterwards to verify.",
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
