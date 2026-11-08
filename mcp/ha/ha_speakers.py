"""MCP server (stdio, newline JSON-RPC): speakers through Home Assistant media players.
Tools: list_speakers (read), find_radio_stream (read, public Radio Browser directory), speak (TTS), play_stream, group_speakers, control (write).
Generic: speakers are discovered from HA (a media player is a TV if its device class is tv or its name says tv/television; everything else is a
speaker); targets resolve by friendly name or entity id; "all" means every available speaker. Every write result carries a plain-language "did" line.
ROYVA_DRY_RUN=1 makes every write a no-op that reports what it WOULD do."""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ha_registry                                                   # noqa: E402  (vendored helper; private HA connection)

DRY_FLAG = Path(os.environ.get("ROYVA_DRY_RUN_FLAG", Path(__file__).resolve().parents[2] / "runtime" / "gateway" / "dry_run"))
DRY = lambda: os.environ.get("ROYVA_DRY_RUN") == "1" or DRY_FLAG.exists()        # rehearsal mode: env var OR the flag file (toggle without a restart)
MAX_TEXT = 1500
RADIO_HOSTS = ["de1.api.radio-browser.info", "nl1.api.radio-browser.info", "at1.api.radio-browser.info"]
ACTIONS = {"pause": ("media_pause", {}), "resume": ("media_play", {}), "play": ("media_play", {}), "stop": ("media_stop", {}),
           "next": ("media_next_track", {}), "previous": ("media_previous_track", {}), "mute": ("volume_mute", {"is_volume_muted": True}),
           "unmute": ("volume_mute", {"is_volume_muted": False}), "volume_up": ("volume_up", {}), "volume_down": ("volume_down", {}),
           "unjoin": ("unjoin", {})}
HINT = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
RO = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
TARGETS = {"type": "array", "items": {"type": "string"}, "description": "Speaker names or entity ids, or [\"all\"] for every available speaker."}


def tool(name, desc, props, required, ann):
    return {"name": name, "description": desc, "inputSchema": {"type": "object", "properties": props, "required": required, "additionalProperties": False}, "annotations": ann}


TOOLS = [
    tool("list_speakers", "List the speakers (not TVs) with name, entity id, platform, state, volume and whether they can be grouped for synchronized playback.", {}, [], RO),
    tool("find_radio_stream", "Find internet radio stations by name in the public Radio Browser directory; returns stream URLs to pass to play_stream.",
         {"query": {"type": "string"}, "country": {"type": "string", "description": "Optional country name to narrow results."}, "limit": {"type": "integer", "default": 5}}, ["query"], RO),
    tool("speak", "Speak text aloud on speakers using text-to-speech. For long content (news, summaries) pass a short spoken script. Changes what the house does; say plainly what was played and where.",
         {"text": {"type": "string"}, "speakers": TARGETS, "volume": {"type": "number", "description": "Optional 0-1 (or 0-100) volume set before speaking."}}, ["text", "speakers"], HINT),
    tool("play_stream", "Play an audio stream URL (for example a radio station) on speakers. Set synced=true to play in sync on grouped speakers (Sonos speakers can be grouped; others play separately and the result says so).",
         {"url": {"type": "string"}, "speakers": TARGETS, "synced": {"type": "boolean", "default": False}, "volume": {"type": "number"}}, ["url", "speakers"], HINT),
    tool("group_speakers", "Group speakers so they play in sync (only speakers that support grouping, such as Sonos). The first speaker is the leader unless leader is given.",
         {"speakers": TARGETS, "leader": {"type": "string"}}, ["speakers"], HINT),
    tool("control", "Control playback or volume on speakers. action: pause, resume, stop, next, previous, mute, unmute, volume_up, volume_down, unjoin, or set_volume (with value 0-1 or 0-100).",
         {"action": {"type": "string", "enum": sorted(list(ACTIONS) + ["set_volume"])}, "speakers": TARGETS, "value": {"type": "number"}}, ["action", "speakers"], HINT),
]


def norm(t) -> str:
    return re.sub(r"[^a-z0-9]", "", str(t).lower())


def speakers_from(states: list, platforms: dict) -> list:
    out = []
    for s in states:
        if not s["entity_id"].startswith("media_player."):
            continue
        a = s["attributes"]
        name = a.get("friendly_name") or s["entity_id"]
        is_tv = a.get("device_class") == "tv" or re.search(r"\b(tv|television)\b", name, re.I)
        if is_tv:
            continue
        sf = a.get("supported_features", 0)
        out.append({"entity_id": s["entity_id"], "name": name, "platform": platforms.get(s["entity_id"], "?"), "state": s["state"],
                    "volume": a.get("volume_level"), "can_group": bool(sf & 4194304), "can_play_media": bool(sf & 512), "group_members": a.get("group_members")})
    return out


def resolve(targets, speakers: list) -> dict:
    """-> {'ok': [speaker...], 'skipped': [reason...], 'error': str|None}. Never guesses on ambiguity; unavailable speakers are skipped and reported."""
    if isinstance(targets, str):
        targets = [targets]
    ok, skipped = [], []

    def take(sp):
        if sp["state"] == "unavailable":
            skipped.append(f"{sp['name']} (unavailable)")
        elif sp not in ok:
            ok.append(sp)

    if any(norm(t) == "all" for t in targets):
        for sp in speakers:
            take(sp)
        return {"ok": ok, "skipped": skipped, "error": None if ok else "no speaker is available"}
    for t in targets:
        q = norm(t)
        exact = [sp for sp in speakers if q in (norm(sp["entity_id"]), norm(sp["name"]))]
        hits = exact or [sp for sp in speakers if q and q in norm(sp["name"])]
        if not hits:
            return {"ok": [], "skipped": skipped, "error": f"no speaker matches '{t}'; known speakers: {[s['name'] for s in speakers]}"}
        if len(hits) > 1:
            return {"ok": [], "skipped": skipped, "error": f"'{t}' is ambiguous: {[h['name'] for h in hits]}"}
        take(hits[0])
    return {"ok": ok, "skipped": skipped, "error": None if ok else "none of the requested speakers is available"}


def volume01(v):
    v = float(v)
    return round(v / 100.0 if v > 1 else v, 3)


def _frac(name, default):
    try:
        return volume01(os.environ.get(name, default))
    except ValueError:
        return default


def max_volume():       # household ceiling: no request can set speakers louder than this (owner choice: 25-30%)
    return _frac("ROYVA_MAX_VOLUME", 0.30)


def play_volume():      # level used whenever a request does not name one
    return min(_frac("ROYVA_PLAY_VOLUME", 0.28), max_volume())


def capped(v):
    return min(volume01(v), max_volume())


class Home:
    """Home Assistant access; every WRITE goes through call() so dry-run and recording are in one place."""
    def __init__(self, get=None, post=None, platforms=None):
        self._get, self._post, self._platforms = get or _get, post or _post, platforms
        self.calls = []

    def speakers(self):
        if self._platforms is None:                                     # real deployment: platform names come from the entity registry
            self._platforms = {e["entity_id"]: e.get("platform") for e in ha_registry.snapshot()["entities"].values()}
        return speakers_from(self._get("/api/states"), self._platforms)

    def call(self, domain, service, data):
        self.calls.append((domain, service, data))
        if DRY():
            return {"dry_run": True}
        if domain == "media_player" and "volume_level" in data:          # the ceiling applies to every path, including the model's own set_volume
            data = {**data, "volume_level": capped(data["volume_level"])}
        if (domain, service) == ("tts", "speak"):                        # HA holds this call open while the speech plays: a timeout means "started", never retry
            try:
                return {"http_status": self._post(f"/api/services/{domain}/{service}", data, timeout=8)}
            except (TimeoutError, OSError) as e:
                if "timed out" in str(e):
                    return {"http_status": 202, "note": "speech started (HA still playing)"}
                raise
        return {"http_status": self._post(f"/api/services/{domain}/{service}", data)}


def _base_and_token():
    ws_url, token = ha_registry._connection()
    return ws_url.replace("wss://", "https://").replace("ws://", "http://").replace("/api/websocket", ""), token


def _get(path):
    base, token = _base_and_token()
    with urllib.request.urlopen(urllib.request.Request(base + path, headers={"Authorization": f"Bearer {token}"}), timeout=20) as r:
        return json.load(r)


def _post(path, body, timeout=60):
    base, token = _base_and_token()
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST", headers={"Authorization": f"Bearer {token}", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status


def _names(sps):
    return ", ".join(s["name"] for s in sps)


def _result(did, targets, skipped, extra=None):
    out = {"ok": True, "did": ("[DRY RUN, nothing happened] " if DRY() else "") + did, "speakers": [s["name"] for s in targets], "skipped": skipped, "dry_run": DRY() or None}
    out.update(extra or {})
    return out


def list_speakers(args, home=None):
    return {"speakers": (home or Home()).speakers()}


PRESETS = Path(os.environ.get("ROYVA_RADIO_PRESETS", Path(__file__).resolve().parents[2] / "runtime" / "gateway" / "radio_presets.json"))


def load_presets(path=None) -> dict:
    """Owner-maintained {name: stream url}. Missing or corrupt file = no presets."""
    try:
        return {str(k): str(v) for k, v in json.loads(Path(path or PRESETS).read_text()).items()}
    except (OSError, ValueError):
        return {}


def loosen(query: str) -> str:
    """Drop frequencies and filler words ('98.5', 'FM', 'radio') so 'Station FM 98.5' also tries 'Station'."""
    words = [w for w in re.split(r"\s+", query.strip()) if w and not re.fullmatch(r"\d+(\.\d+)?|fm|am|radio|station|live", w, re.I)]
    return " ".join(words)


def find_radio_stream(args, fetch=None, presets=None):
    query = str(args["query"])
    pre = load_presets() if presets is None else presets
    hits = [{"name": n, "url": u, "preset": True} for n, u in pre.items() if norm(n) and (norm(n) in norm(query) or norm(query) in norm(n))]
    if hits:
        return {"stations": hits, "note": "from the owner's saved presets"}
    out = _radio_search(query, args, fetch)
    if out.get("stations") or out.get("error"):
        return out
    looser = loosen(query)
    if looser and looser.lower() != query.lower():
        out = _radio_search(looser, args, fetch)
        if out.get("stations"):
            return {**out, "note": f"no exact match for '{query}'; these match '{looser}'"}
    return {"stations": [], "hint": "No station by that name in the public directory. Ask the owner for its stream URL (it can be saved as a preset), or search by genre or city."}


def _radio_search(query, args, fetch=None):
    q = urllib.parse.urlencode({"name": query, "limit": int(args.get("limit", 5)), "hidebroken": "true", "order": "votes", "reverse": "true",
                                **({"country": args["country"]} if args.get("country") else {})})
    last = None
    for host in RADIO_HOSTS:
        try:
            req = urllib.request.Request(f"https://{host}/json/stations/search?{q}", headers={"User-Agent": "RoyVa/1.0"})
            rows = fetch(req) if fetch else json.load(urllib.request.urlopen(req, timeout=15))
            return {"stations": [{"name": r.get("name"), "url": r.get("url_resolved") or r.get("url"), "codec": r.get("codec"), "bitrate": r.get("bitrate"),
                                  "country": r.get("country"), "state": r.get("state"), "votes": r.get("votes")} for r in rows]}
        except Exception as e:                                          # noqa: BLE001
            last = e
    return {"error": f"radio directory unreachable: {type(last).__name__}"}


def _vol(home, targets, volume):
    level = play_volume() if volume is None else capped(volume)          # always set a safe level before anything plays
    home.call("media_player", "volume_set", {"entity_id": [t["entity_id"] for t in targets], "volume_level": level})


def speak(args, home=None):
    home = home or Home()
    r = resolve(args["speakers"], home.speakers())
    if r["error"]:
        return {"ok": False, "error": r["error"]}
    text = str(args["text"]).strip()
    if not text:
        return {"ok": False, "error": "nothing to say"}
    truncated = len(text) > MAX_TEXT
    text = text[:MAX_TEXT]
    tts = os.environ.get("ROYVA_TTS_ENTITY") or next((s["entity_id"] for s in home._get("/api/states") if s["entity_id"].startswith("tts.")), None)
    if not tts:
        return {"ok": False, "error": "no text-to-speech engine is configured in Home Assistant"}
    _vol(home, r["ok"], args.get("volume"))
    home.call("tts", "speak", {"entity_id": tts, "media_player_entity_id": [t["entity_id"] for t in r["ok"]], "message": text})
    return _result(f"Spoke {len(text)} characters ({'truncated' if truncated else 'complete'}) on {_names(r['ok'])}", r["ok"], r["skipped"], {"truncated": truncated})


def group_speakers(args, home=None):
    home = home or Home()
    r = resolve(args["speakers"], home.speakers())
    if r["error"]:
        return {"ok": False, "error": r["error"]}
    groupable = [s for s in r["ok"] if s["can_group"]]
    loose = [s["name"] + " (cannot be grouped)" for s in r["ok"] if not s["can_group"]]
    if len(groupable) < 2:
        return {"ok": False, "error": "need at least two speakers that support grouping", "skipped": r["skipped"] + loose}
    lead = groupable[0]
    if args.get("leader"):
        q = norm(args["leader"])
        picks = [s for s in groupable if q in (norm(s["name"]), norm(s["entity_id"]))] or [s for s in groupable if q and q in norm(s["name"])]
        if len(picks) != 1:                                                  # an unknown or ambiguous leader is an error, never a silent default
            return {"ok": False, "error": f"leader '{args['leader']}' " + ("is ambiguous" if picks else "is not one of the groupable speakers"),
                    "groupable": [s["name"] for s in groupable]}
        lead = picks[0]
    members = [s for s in groupable if s is not lead]
    home.call("media_player", "join", {"entity_id": lead["entity_id"], "group_members": [m["entity_id"] for m in members]})
    return _result(f"Grouped {_names(groupable)} with {lead['name']} as leader", groupable, r["skipped"] + loose, {"leader": lead["name"]})


def play_stream(args, home=None):
    home = home or Home()
    url = str(args["url"])
    if not re.match(r"^https?://", url):
        return {"ok": False, "error": "url must start with http:// or https://"}
    r = resolve(args["speakers"], home.speakers())
    if r["error"]:
        return {"ok": False, "error": r["error"]}
    playable = [s for s in r["ok"] if s["can_play_media"]]
    if not playable:
        return {"ok": False, "error": "none of those speakers can play a stream"}
    _vol(home, playable, args.get("volume"))
    notes = []
    if args.get("synced") and len(playable) > 1:
        groupable = [s for s in playable if s["can_group"]]
        others = [s for s in playable if not s["can_group"]]
        if len(groupable) > 1:
            lead, members = groupable[0], groupable[1:]
            home.call("media_player", "join", {"entity_id": lead["entity_id"], "group_members": [m["entity_id"] for m in members]})
            home.call("media_player", "play_media", {"entity_id": lead["entity_id"], "media_content_id": url, "media_content_type": "music"})
            notes.append(f"{_names(groupable)} play in sync (grouped under {lead['name']})")
        elif groupable:
            others = playable
        if others:
            home.call("media_player", "play_media", {"entity_id": [s["entity_id"] for s in others], "media_content_id": url, "media_content_type": "music"})
            notes.append(f"{_names(others)} play separately, NOT in sync" if groupable and len(groupable) > 1 else f"{_names(others)} play (not grouped)")
    else:
        home.call("media_player", "play_media", {"entity_id": [s["entity_id"] for s in playable], "media_content_id": url, "media_content_type": "music"})
        notes.append(f"{_names(playable)} play")
    return _result("Started stream: " + "; ".join(notes), playable, r["skipped"] + [s["name"] + " (cannot play streams)" for s in r["ok"] if not s["can_play_media"]], {"url": url})


def control(args, home=None):
    home = home or Home()
    r = resolve(args["speakers"], home.speakers())
    if r["error"]:
        return {"ok": False, "error": r["error"]}
    act, ids = args["action"], [s["entity_id"] for s in r["ok"]]
    if act == "set_volume":
        if args.get("value") is None:
            return {"ok": False, "error": "set_volume needs a value between 0 and 1 (or 0 to 100)"}
        home.call("media_player", "volume_set", {"entity_id": ids, "volume_level": volume01(args["value"])})
        did = f"Set volume to {round(capped(args['value']) * 100)}% on {_names(r['ok'])}" + (f" (limited from {round(volume01(args['value']) * 100)}%: household maximum is {round(max_volume() * 100)}%)" if volume01(args["value"]) > max_volume() else "")
    elif act in ACTIONS:
        service, extra = ACTIONS[act]
        home.call("media_player", service, {"entity_id": ids, **extra})
        did = f"{act.replace('_', ' ').capitalize()} on {_names(r['ok'])}"
    else:
        return {"ok": False, "error": f"unknown action '{act}'"}
    return _result(did, r["ok"], r["skipped"])


FUNCS = {"list_speakers": list_speakers, "find_radio_stream": find_radio_stream, "speak": speak, "play_stream": play_stream, "group_speakers": group_speakers, "control": control}


def handle(msg):
    method, ident = msg.get("method"), msg.get("id")
    if method == "initialize":
        result = {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}}, "serverInfo": {"name": "ha-speakers", "version": "1.0.0"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        p = msg.get("params", {})
        try:
            result = {"content": [{"type": "text", "text": json.dumps(FUNCS[p.get("name")](p.get("arguments", {})))}]}
        except Exception as e:                                          # noqa: BLE001
            result = {"content": [{"type": "text", "text": json.dumps({"ok": False, "error": str(e)[:300]})}], "isError": True}
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
