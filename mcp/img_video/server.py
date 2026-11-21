"""MCP server (stdio, newline JSON-RPC): a thin RoyVa wrapper around the img_video agent (agents/img_video). It holds no image logic of its own and never talks to the GPU box itself.
Tools:
  generate_image(prompt, width, height, seed)    ONE picture from the user's own words: shortened by the agent's guard if long, drawn on the 3090 (this machine's GPU if the box is down). Immediate.
  generate_image_set(query, count, aspect)       a SET of pictures planned by the director (web research when needed, one caption each). Starts a background job and returns AT ONCE.
  generate_video(query, count, aspect)           a video planned by the director, which decides whether it needs a voice-over (an explanation) or none (a pure clip). Starts a background job and returns AT ONCE.
Two modes, chosen per call by the flag file runtime/gateway/img_video_async (absent = SYNCHRONOUS, the default: the tool waits and returns the pictures with their captions / the video path, so the bridge's live progress bar, Stop, usage lines and captions work as for any tool; present = BACKGROUND: the call returns at once, runner.py runs detached and leaves the result in the outbox and the Telegram bridge posts it when it is ready). One director job at a time (a lock the runner keeps
while it runs), honors the dry-run flag. Overrides: ROYVA_IMAGE_DIR, ROYVA_OUTBOX_DIR, ROYVA_IMGVIDEO_TIMEOUT, ROYVA_IMGVIDEO_CMD (JSON list, for tests)."""
import fcntl
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))               # mcp/stdio_cancel.py (shared)
import stdio_cancel  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AGENT_DIR = Path(os.environ.get("ROYVA_IMGVIDEO_DIR", ROOT / "agents" / "img_video"))
IMAGE_DIR = Path(os.environ.get("ROYVA_IMAGE_DIR", ROOT / "runtime" / "data" / "images"))
OUTBOX = Path(os.environ.get("ROYVA_OUTBOX_DIR", ROOT / "runtime" / "data" / "outbox"))
INBOX = Path(os.environ.get("ROYVA_INBOX_DIR", ROOT / "runtime" / "data" / "inbox"))      # photos the bridge saved from chat: the only place reference photos are read from
LOCK = Path(os.environ.get("ROYVA_IMGVIDEO_LOCK", ROOT / "runtime" / "gateway" / "img_video.lock"))
DRY_FLAG = Path(os.environ.get("ROYVA_DRY_RUN_FLAG", ROOT / "runtime" / "gateway" / "dry_run"))
ASYNC_FLAG = Path(os.environ.get("ROYVA_IMGVIDEO_ASYNC_FLAG", ROOT / "runtime" / "gateway" / "img_video_async"))
ASYNC = lambda: os.environ.get("ROYVA_IMGVIDEO_ASYNC") == "1" or (os.environ.get("ROYVA_IMGVIDEO_ASYNC") != "0" and ASYNC_FLAG.exists())      # checked on every call: touch/remove the flag file to switch, no restart
SYNC_TIMEOUT = {"set": int(os.environ.get("ROYVA_IMGSET_SYNC_TIMEOUT", "900")), "video": int(os.environ.get("ROYVA_IMGVIDEO_SYNC_TIMEOUT", "2700"))}
sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner
DRY = lambda: os.environ.get("ROYVA_DRY_RUN") == "1" or DRY_FLAG.exists()
SINGLE_TIMEOUT = int(os.environ.get("ROYVA_IMAGE_TIMEOUT", "600"))
OC_DB = Path(os.environ.get("ROYVA_OPENCODE_DB", ROOT / "runtime" / "data" / "opencode" / "opencode.db"))      # OpenCode's own record of every message, read-only here
MAX_QUERY, MAX_COUNT, MAX_PROMPT = 1000, 30, 6000
MAX_SECONDS = 600                      # a sanity bound on what the chat model passes; the agent applies the real limit ([limits] max_video_seconds)
MAX_RESEARCH = 6000          # facts the caller already found; longer text is clipped, never rejected (a rejection only makes the caller retry)
MIN_SIDE, MAX_SIDE, KEEP_SINGLE = 512, 1280, 60
ASPECTS = ("9:16", "16:9", "1:1")
HINT = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True}
MAX_PHOTOS = 6
PHOTO_TYPES = (".jpg", ".jpeg", ".png", ".webp")
ASPECT_PROP = {"type": "string", "enum": list(ASPECTS), "default": "1:1", "description": "Shape of each picture or of the video."}

REFERENCE_PROP = {"type": "array", "maxItems": MAX_PHOTOS, "items": {"anyOf": [{"type": "string"}, {"type": "object", "properties": {"path": {"type": "string"}, "who": {"type": "string"}}, "required": ["path"], "additionalProperties": False}]},
                  "description": "OPTIONAL. The photos of the people (or the pet, car, product or other thing) who must appear in the story, from the user's [Attached photo: path] lines, in the order they were sent. Each item is the path exactly as written (never invent one), or {\"path\": ..., \"who\": ...} where `who` is what the user called that person "
                  "(\"me\", \"my wife\", \"the man\") when the message says so. Several photos can show the same person. The pictures keep each person's likeness (or the thing's look) and the story gives people a role and an outfit. Leave it out when the user attached no photo."}

TOOLS = [
    {"name": "generate_image",
     "description": ("Pictures only: NEVER use this for a video, clip or animation request. Draw ONE picture from a text description and send it to the chat. The description is used as written (a very long one is shortened automatically); nothing is planned or added. "
                     "Takes about 15 seconds on the GPU box. For several pictures use the set tool, for a video the video tool."),
     "inputSchema": {"type": "object", "properties": {
         "prompt": {"type": "string", "description": "What the picture should show, in English. About 500 characters is plenty; a longer description is shortened automatically."},
         "width": {"type": "integer", "default": 1024, "description": f"Multiple of 16, {MIN_SIDE}-{MAX_SIDE}."}, "height": {"type": "integer", "default": 1024, "description": f"Multiple of 16, {MIN_SIDE}-{MAX_SIDE}."},
         "seed": {"type": "integer", "description": "Optional, for a repeatable result."}}, "required": ["prompt"], "additionalProperties": False}, "annotations": HINT},
    {"name": "generate_image_set",
     "description": ("Pictures only: NEVER use this for a video, clip or animation request. Make a SET of several pictures from one request, for example '10 images of today's top headlines in a sarcastic tone' or '6 pictures explaining the water cycle'. "
                     "It plans the set, looks up current facts on the web when the request needs them, writes a caption for each picture and draws them. It takes a few minutes, so it runs in the background and this call "
                     "RETURNS AT ONCE; the pictures are posted to the chat, each with its caption, when they are ready. Call it ONCE per request and pass the user's request in their own words, including anything they said "
                     "about the captions or the tone. When it returns, reply with ONE short sentence saying it has started and will be posted here when ready."),
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "What the set should show, in the user's words (include the tone or style they asked for and anything about what the captions should say)."},
         "count": {"type": "integer", "description": f"How many pictures, 1-{MAX_COUNT}. Omit it unless the user gave a number."}, "aspect": ASPECT_PROP, "reference_photos": REFERENCE_PROP}, "required": ["query"], "additionalProperties": False}, "annotations": HINT},
    {"name": "generate_video",
     "description": ("Make a VIDEO from one request: pictures planned and animated, joined in order. The director decides whether it needs a voice-over (an explanation, a lesson, a story, the news) or none (a pure clip). "
                     "It takes several minutes, so it runs in the background and this call RETURNS AT ONCE; the video is posted to the chat when it is ready. Call it ONCE per request and pass the user's request in "
                     "their own words. When it returns, reply with ONE short sentence saying it has started and will be posted here when ready."),
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "What the video should show or explain, in the user's words (include any tone, style or narration wishes)."},
         "research_text": {"type": "string", "description": "OPTIONAL. Only if you ALREADY searched the web for this request: the key facts you found (up to about 6000 characters). The video then skips its own web search. Keep `query` short and put facts here, never in `query`."},
         "count": {"type": "integer", "description": f"How many scenes, 1-{MAX_COUNT}. Omit it unless the user gave a number."},
         "seconds": {"type": "integer", "description": f"OPTIONAL. The length of the video in seconds when the user states one (\"1 minute\" is 60, \"a minute and a half\" is 90, \"30 seconds\" is 30), 1-{MAX_SECONDS}. Omit it when the user gave no length. Always pass it when they did."},
         "aspect": ASPECT_PROP, "reference_photos": REFERENCE_PROP}, "required": ["query"], "additionalProperties": False}, "annotations": HINT},
]


SYNC_TEXT = {"generate_image_set": ("Pictures only: NEVER use this for a video, clip or animation request. Make a SET of several pictures from one request, for example '10 images of today's top headlines in a sarcastic tone' or '6 pictures explaining the water cycle'. It plans the set, looks up current facts on the web "
                                     "when the request needs them, writes a caption for each picture and draws them. It takes a few minutes and the pictures are sent to the chat, each with its caption, when it returns. Call it ONCE per request and pass the "
                                     "user's request in their own words, including anything they said about the captions or the tone. When it returns, reply with ONE short sentence as its result says."),
             "generate_video": ("Make a VIDEO from one request: pictures planned and animated, joined in order. The director decides whether it needs a voice-over (an explanation, a lesson, a story, the news) or none (a pure clip). "
                                "It takes several minutes and the video is sent to the chat when it returns. Call it ONCE per request and pass the user's request in their own words. When it returns, reply with ONE short sentence as its result says.")}


def tools_for_mode():
    if ASYNC(): return TOOLS
    return [({**t, "description": SYNC_TEXT[t["name"]]} if t["name"] in SYNC_TEXT else t) for t in TOOLS]


def _with_album_mates(photos):
    """The photos the user sent in the SAME message (the bridge records an album in inbox/.albums/*.json): any the chat model left out are added, in the order they were sent, with the labels it gave kept. Never more than MAX_PHOTOS."""
    given = {Path(p).name: w for p, w in photos}; order = []
    for f in sorted((INBOX / ".albums").glob("*.json")) if (INBOX / ".albums").is_dir() else []:
        try: files = [n for n in json.loads(f.read_text()).get("files", []) if isinstance(n, str)]
        except (OSError, ValueError): continue
        if given.keys() & set(files):
            for n in files:
                if n not in order: order.append(n)
    if not order: return photos
    rest = [n for n in given if n not in order]
    out = []
    for n in order + rest:
        path = (INBOX / n).resolve()
        if INBOX.resolve() in path.parents and path.suffix.lower() in PHOTO_TYPES and path.is_file(): out.append((str(path), given.get(n, "")))
    return out[:MAX_PHOTOS] or photos


def _side(v, name):
    v = int(v)
    if not MIN_SIDE <= v <= MAX_SIDE or v % 16: raise ValueError(f"{name} must be a multiple of 16 between {MIN_SIDE} and {MAX_SIDE}")
    return v


def _prune_single():
    for f in sorted(IMAGE_DIR.glob("img-*.png"), key=lambda p: p.stat().st_mtime, reverse=True)[KEEP_SINGLE:]:
        try: f.unlink()
        except OSError: pass


def generate_image(args):
    prompt = str(args.get("prompt", "")).strip()
    if not prompt: return {"ok": False, "error": "prompt is empty"}
    if len(prompt) > MAX_PROMPT: return {"ok": False, "error": f"prompt is too long ({len(prompt)} > {MAX_PROMPT} characters)"}
    width, height = _side(args.get("width", 1024), "width"), _side(args.get("height", 1024), "height")
    if DRY(): return {"ok": True, "did": f"[DRY RUN, nothing happened] Would draw a {width}x{height} picture: {prompt[:80]}"}
    cmd = (json.loads(os.environ["ROYVA_IMGVIDEO_IMAGE_CMD"]) if os.environ.get("ROYVA_IMGVIDEO_IMAGE_CMD") else
           ["/usr/bin/python3", "-m", "img_video", "image", "--stdin", "--json", "--size", f"{width}x{height}"] + (["--seed", str(int(args["seed"]))] if args.get("seed") is not None else []))
    try:
        p = stdio_cancel.run(cmd, input=prompt, cwd=AGENT_DIR, capture_output=True, text=True, timeout=SINGLE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"the picture did not finish within {SINGLE_TIMEOUT} s"}
    lines = [l for l in p.stdout.splitlines() if l.strip().startswith("{")]
    if not lines: return {"ok": False, "error": "the picture agent returned nothing usable: " + (p.stderr.strip().splitlines() or ["no output"])[-1][:200]}
    res = json.loads(lines[-1])
    if not res.get("ok"): return {"ok": False, "error": str(res.get("error") or "the picture agent failed")[:300]}
    src = Path(res["image_path"])
    if not src.is_file(): return {"ok": False, "error": "the picture is missing on disk"}
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    dst = IMAGE_DIR / f"img-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}.png"; shutil.copy2(src, dst); _prune_single()
    where = "on the GPU box" if res.get("backend") == "3090" else "on this machine's GPU"
    short = f" The description was {res['original_chars']} characters, so it was shortened to {res['chars']} ({res['method']}) first." if res.get("method") not in (None, "none") else ""
    return {"ok": True, "did": f"Drew a {res['width']}x{res['height']} picture {where} in {res['secs']}s (seed {res['seed']}); it is sent to the chat.{short} {res.get('note') or ''}".strip(),
            "image_path": str(dst), "seed": res["seed"], "secs": res["secs"], "backend": "comfyui" if res.get("backend") == "3090" else "local"}


def raw_message(photo_paths):
    """The user's own words for a request that has photos. The chat model rewrites the request before it calls the tool (and has changed colors, lengths and aspects in the rewrite), but OpenCode keeps the message as the user sent it,
    ending with the "[Attached photo: <path>]" lines: find the newest message that contains one of these photos and return its text without the gateway's <context> block and without those lines. None when it cannot be found (the caller then keeps the chat model's query)."""
    try:
        con = sqlite3.connect(f"file:{OC_DB}?mode=ro", uri=True, timeout=2)
        try:
            for name in [Path(p).name for p in photo_paths]:
                for (data,) in con.execute("select data from session_message where instr(cast(data as text), ?) > 0 order by rowid desc limit 10", (name,)):
                    text = json.loads(data).get("text")
                    if not isinstance(text, str): continue                                     # the assistant's rows have no "text"
                    text = re.sub(r"^\s*<context>.*?</context>\s*", "", text, flags=re.S)
                    text = re.sub(r"^\[Attached photo: .*\]\s*$", "", text, flags=re.M).strip()
                    if text: return text[:MAX_QUERY]
        finally:
            con.close()
    except Exception:                                                                          # noqa: BLE001  no database, a different layout, bad JSON: fall back to what the chat model passed
        pass
    return None


def _start(kind, args):
    query = str(args.get("query", "")).strip()
    what = "picture set" if kind == "set" else "video"
    if not query: return [{"ok": False, "error": "query is empty"}]
    if len(query) > MAX_QUERY: return [{"ok": False, "error": f"query is too long ({len(query)} > {MAX_QUERY} characters)"}]
    count = args.get("count")
    if count is not None:
        count = int(count)
        if not 1 <= count <= MAX_COUNT: return [{"ok": False, "error": f"count must be 1-{MAX_COUNT}"}]
    seconds = args.get("seconds") if kind == "video" else None
    if seconds is not None:
        try: seconds = int(seconds)
        except (TypeError, ValueError): return [{"ok": False, "error": f"seconds must be a number 1-{MAX_SECONDS}"}]
        if not 1 <= seconds <= MAX_SECONDS: return [{"ok": False, "error": f"seconds must be 1-{MAX_SECONDS}"}]
    aspect = str(args.get("aspect", "1:1"))
    if aspect not in ASPECTS: return [{"ok": False, "error": f"aspect must be one of {', '.join(ASPECTS)}"}]
    photos = []
    for item in list(args.get("reference_photos") or [])[:MAX_PHOTOS]:
        raw, who = (item.get("path"), str(item.get("who") or "").strip()[:60].replace("|", " ")) if isinstance(item, dict) else (item, "")
        src = Path(str(raw)).expanduser().resolve()
        if INBOX.resolve() not in src.parents or src.suffix.lower() not in PHOTO_TYPES or not src.is_file():
            return [{"ok": False, "error": f"reference photo {Path(str(raw)).name!r} is not one of the photos the user sent in this chat (jpg, png or webp); use the path from the [Attached photo: ...] line"}]
        photos.append((str(src), who))
    photos = _with_album_mates(photos)
    chat_query = query
    if photos: query = raw_message([p for p, _w in photos]) or query                    # the user's own words, not the chat model's rewrite
    photos = [p + (f"|{w}" if w else "") for p, w in photos]
    if DRY(): return [{"ok": True, "did": f"[DRY RUN, nothing happened] Would start a {what} ({count or 'several'} pictures, {aspect}) for: {query[:100]}"}]
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock = open(LOCK, "w")
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close(); return [{"ok": False, "error": f"another picture set or video is still being made; ask again in a few minutes"}]
    job = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    spec = {"job": job, "kind": kind, "query": query, **({"chat_query": chat_query} if chat_query != query else {}), "count": count, "aspect": aspect, **({"seconds": seconds} if seconds else {}), **({"references": photos} if photos else {})}
    research = str(args.get("research_text") or "").strip()[:MAX_RESEARCH]
    if research and kind == "video": spec["research_text"] = research
    if not ASYNC():                                                  # synchronous: wait for the job and return it as this tool's result (the lock is held by this process meanwhile)
        try: return _sync_parts(kind, runner.produce({**spec, "timeout": SYNC_TIMEOUT[kind]}))
        finally: lock.close()
    try:
        (OUTBOX / "logs").mkdir(parents=True, exist_ok=True)
        log = open(OUTBOX / "logs" / f"{job}.log", "w")
        subprocess.Popen([sys.executable, str(HERE / "runner.py"), json.dumps(spec)], cwd=AGENT_DIR, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True, pass_fds=(lock.fileno(),))
        log.close()
    except Exception as e:                                           # noqa: BLE001
        lock.close(); return [{"ok": False, "error": f"could not start the {what}: {str(e)[:200]}"}]
    lock.close()                                                     # the runner's inherited copy keeps the lock until it exits
    eta = "a few minutes" if kind == "set" else "about five minutes"
    return [{"ok": True, "async_job": job, "kind": kind, "did": f"Started: the {what} is being made in the background and will be posted to this chat when it is ready ({eta}). Reply with one short sentence saying so."}]


def _sync_parts(kind, payload):
    """The synchronous result in the format the bridge already understands: one text part per picture with image_path and caption (a summary part last), or a video_path for a video."""
    if not payload.get("ok"): return [{"ok": False, "error": str(payload.get("error") or "it failed")[:300]}]
    secs = payload.get("stage_seconds") or {}
    if kind == "video":
        v = payload["video"]; return [{"ok": True, "did": f"Made a {v.get('seconds')} s video ({payload.get('title', '')}); it is sent to the chat. Reply with one short sentence.", "video_path": v["path"], "seconds": v.get("seconds"), "title": payload.get("title", ""), "stage_seconds": secs}]
    imgs = payload["images"]; each = round((secs.get("images") or 0) / max(1, len(imgs)), 1)
    parts = [{"ok": True, "image_path": im["path"], "index": im["index"], "topic": im["topic"], "caption": im["caption"], "secs": each} for im in imgs]
    parts.append({"ok": True, "did": f"Made {len(imgs)} pictures ({payload.get('title', '')}); they are sent to the chat with their captions attached. Reply with one short sentence.", "stage_seconds": secs})
    return parts


def generate_image_set(args): return _start("set", args)


def generate_video(args): return _start("video", args)


FUNCS = {"generate_image": generate_image, "generate_image_set": generate_image_set, "generate_video": generate_video}


def handle(msg):
    method, ident = msg.get("method"), msg.get("id")
    if method == "initialize":
        result = {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}}, "serverInfo": {"name": "img-video", "version": "2.0.0"}}
    elif method == "tools/list":
        result = {"tools": tools_for_mode()}
    elif method == "tools/call":
        p = msg.get("params", {})
        try:
            parts = FUNCS[p.get("name")](p.get("arguments", {}))
            result = {"content": [{"type": "text", "text": json.dumps(x)} for x in (parts if isinstance(parts, list) else [parts])]}
        except Exception as e:                                          # noqa: BLE001
            result = {"content": [{"type": "text", "text": json.dumps({"ok": False, "error": str(e)[:300]})}], "isError": True}
    elif ident is None:
        return
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "Method not found"}}), flush=True)
        return
    print(json.dumps({"jsonrpc": "2.0", "id": ident, "result": result}), flush=True)


if __name__ == "__main__":
    stdio_cancel.serve(handle)                                          # reads stdin while a tool runs, so Stop (notifications/cancelled) reaches it
