"""Read-only MCP server (stdio, newline JSON-RPC) for numeric Home Assistant entity history.
Tools: find_entities (search by name/id), get_numeric_change (first/last/change/min/max of a numeric entity over a time window).
Typical use: vehicle distance this week = odometer change over the week. Uses the same private connection as the other ha_* helpers."""
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ha_registry                                                   # noqa: E402  (vendored helper; reads ~/llm-server/ha-remote.json + HA_TOKEN)

FIND = {"name": "find_entities",
        "description": "Search Home Assistant entities by words in their id or friendly name (for example 'odometer', 'car', 'garage door'). "
                       "Returns up to `limit` matches with entity_id, friendly name, current state and unit. Use this to get the exact entity_id first.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "Words to look for."},
                                                         "limit": {"type": "integer", "default": 10}},
                        "required": ["query"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}}
CHANGE = {"name": "get_numeric_change",
          "description": "Numeric history of ONE entity over a time window, in ONE call: first value, last value, change (last - first), min, max and number of readings. "
                         "For a vehicle odometer (total_increasing) the change is the distance travelled in that window. start/end are timezone-aware ISO datetimes; "
                         "omit end for now. Get the exact entity_id from find_entities first, and the current date/time from the date tool.",
          "inputSchema": {"type": "object", "properties": {"entity_id": {"type": "string"},
                                                           "start": {"type": "string", "description": "Inclusive ISO datetime WITH timezone offset."},
                                                           "end": {"type": "string", "description": "Exclusive ISO datetime with timezone offset; omit for now."}},
                          "required": ["entity_id", "start"], "additionalProperties": False},
          "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}}


def _base_and_token():
    ws_url, token = ha_registry._connection()
    return ws_url.replace("wss://", "https://").replace("ws://", "http://").replace("/api/websocket", ""), token


def _get(path):
    base, token = _base_and_token()
    req = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


_DEVICE_TEXT = None


def _device_text():
    """entity_id -> 'device name manufacturer model area' from the registries (so a brand or model word finds a sensor with an opaque id)."""
    global _DEVICE_TEXT
    if _DEVICE_TEXT is None:
        snap = ha_registry.snapshot()
        areas = {a["area_id"]: a["name"] for a in snap["areas"].values()}
        out = {}
        for eid, e in snap["entities"].items():
            d = snap["devices"].get(e.get("device_id"), {})
            bits = [d.get("name_by_user") or d.get("name"), d.get("manufacturer"), d.get("model"), areas.get(e.get("area_id") or d.get("area_id"))]
            out[eid] = " ".join(str(b) for b in bits if b)
        _DEVICE_TEXT = out
    return _DEVICE_TEXT


def find_entities(args):
    q = [w for w in str(args.get("query", "")).lower().split() if w]
    limit = int(args.get("limit", 10))
    out = []
    dev = _device_text()
    for s in _get("/api/states"):
        a = s.get("attributes", {})
        hay = (s["entity_id"] + " " + str(a.get("friendly_name", "")) + " " + dev.get(s["entity_id"], "")).lower()
        if q and all(w in hay for w in q):
            out.append({"entity_id": s["entity_id"], "name": a.get("friendly_name"), "device": dev.get(s["entity_id"]) or None, "state": s["state"],
                        "unit": a.get("unit_of_measurement"), "device_class": a.get("device_class")})
    return {"matches": out[:limit], "total_matches": len(out)}


def _aware(value, name):
    d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError(f"{name} must include a timezone offset")
    return d


def numeric_change(args):
    eid = args["entity_id"]
    start = _aware(args["start"], "start")
    end = _aware(args["end"], "end") if args.get("end") else dt.datetime.now(dt.timezone.utc)
    if end <= start:
        raise ValueError("end must be after start")
    path = (f"/api/history/period/{urllib.parse.quote(start.isoformat())}?filter_entity_id={urllib.parse.quote(eid)}"
            f"&end_time={urllib.parse.quote(end.isoformat())}&minimal_response&no_attributes")
    groups = _get(path)
    rows = groups[0] if groups else []
    vals = []
    for r in rows:
        try:
            vals.append(float(r["state"]))
        except (ValueError, TypeError, KeyError):
            continue                                                    # unavailable / unknown
    if not vals:
        return {"entity_id": eid, "error": "no numeric readings in that window (entity may be non-numeric, unavailable, or outside recorder retention)"}
    cur = next((s for s in _get("/api/states") if s["entity_id"] == eid), {})
    return {"entity_id": eid, "unit": cur.get("attributes", {}).get("unit_of_measurement"), "start": start.isoformat(), "end": end.isoformat(),
            "first": vals[0], "last": vals[-1], "change": round(vals[-1] - vals[0], 3), "min": min(vals), "max": max(vals), "readings": len(vals),
            "note": "change = last - first; for a total_increasing sensor (odometer, energy) this is the amount used/travelled in the window"}


CHANGES = {"name": "get_state_changes",
           "description": "State-change history of ONE entity over a time window, in ONE call: how many times it changed, counts per state, and the most recent changes with timestamps. "
                          "Use it for events and on/off sensors: doorbell/camera events (event.* entities: every change is one event), motion or person sensors "
                          "(how many times it turned on, when it last turned on), doors, appliances. start/end are timezone-aware ISO datetimes; omit end for now.",
           "inputSchema": {"type": "object", "properties": {"entity_id": {"type": "string"},
                                                            "start": {"type": "string", "description": "Inclusive ISO datetime WITH timezone offset."},
                                                            "end": {"type": "string", "description": "Exclusive ISO datetime with timezone offset; omit for now."},
                                                            "recent": {"type": "integer", "default": 10, "description": "How many most-recent changes to list."}},
                           "required": ["entity_id", "start"], "additionalProperties": False},
           "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}}


def state_changes(args):
    eid = args["entity_id"]
    start = _aware(args["start"], "start")
    end = _aware(args["end"], "end") if args.get("end") else dt.datetime.now(dt.timezone.utc)
    if end <= start:
        raise ValueError("end must be after start")
    path = (f"/api/history/period/{urllib.parse.quote(start.isoformat())}?filter_entity_id={urllib.parse.quote(eid)}"
            f"&end_time={urllib.parse.quote(end.isoformat())}&minimal_response&no_attributes")
    groups = _get(path)
    rows = groups[0] if groups else []
    if not rows:
        return {"entity_id": eid, "error": "no history in that window (entity unknown, or outside recorder retention)"}
    # the first row is the state at `start` (not a change inside the window) when its last_changed precedes the window
    inside = [r for r in rows if r.get("last_changed") and _aware(r["last_changed"], "t") >= start]
    blips = [r for r in inside if r["state"] in ("unavailable", "unknown")]               # connectivity changes, not activity
    real = [r for r in inside if r["state"] not in ("unavailable", "unknown")]
    counts = {}
    for r in real:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    recent = [{"state": r["state"], "at": r["last_changed"]} for r in real[-int(args.get("recent", 10)):]][::-1]
    return {"entity_id": eid, "start": start.isoformat(), "end": end.isoformat(), "changes_in_window": len(real), "availability_changes": len(blips),
            "counts_by_state": counts, "most_recent_first": recent, "state_at_start": rows[0]["state"],
            "note": "changes_in_window excludes going unavailable/unknown (reported separately). For event.* entities each real change is one event; "
                    "for on/off sensors count the 'on' entry for how many times it triggered. If the state value itself is a timestamp, it is the time of that event."}


def handle(msg):
    method, ident = msg.get("method"), msg.get("id")
    if method == "initialize":
        result = {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}},
                  "serverInfo": {"name": "ha-entity-history", "version": "1.0.0"}}
    elif method == "tools/list":
        result = {"tools": [FIND, CHANGE, CHANGES]}
    elif method == "tools/call":
        p = msg.get("params", {})
        try:
            fn = {"find_entities": find_entities, "get_numeric_change": numeric_change, "get_state_changes": state_changes}[p.get("name")]
            data = fn(p.get("arguments", {}))
            result = {"content": [{"type": "text", "text": json.dumps(data)}]}
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
        line = line.strip()
        if line:
            try:
                handle(json.loads(line))
            except Exception as e:                                      # noqa: BLE001
                print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)[:200]}}), flush=True)
