"""The director: turns a generic request into a fully specified plan before anything is rendered. The local writer runs WITHOUT thinking mode, so the thinking is done in separate steps, each a
normal call that writes its reasoning into JSON the next step reads:
  1 analyze  : what the request needs, the rules the pictures must obey, which details it leaves open, and the list of shots (more web searches if the material has too few).
  2 decide   : a concrete value for every open detail, plus one style bible for the whole set.
  3 shots    : one call per shot (each sees the earlier shots): which rules apply, a scene spec, caption, motion and narration.
  4 compile  : plain code turns the specs into image prompts, the style line and the video storyboard.
One plan feeds both the pictures and the video; nothing here is specific to a topic. Output: direction.json (the plan), items.json (pictures + captions), and video/storyboard.json."""
import json
import re
import time

from . import llm, research, video
from . import progress
from .guard import cut as _cut

SCENE = ("subject", "setting", "colors")      # subject: who/what + action (+ positions and facing when they matter); setting: where + framing; colors: key colors + light
HEX = re.compile(r"\s*\(?#[0-9A-Fa-f]{6}\)?")
LABEL = re.compile(r"\b[Ss]hot \d+\s*[:\-\u2013]\s*")
NONE = re.compile(r"^\s*(n/?a|none|not applicable|-)\s*\.?\s*$", re.I)


def _facts(res): return "\n\n".join(f"[{r['question'][:80]}]\n{r['text']}" for r in res) or "(no web research was needed)"


def _s(o, k): return isinstance(o.get(k), str) and bool(o[k].strip())


def _as_list(o, *keys):
    """The model often answers a list field as an object ({"lighting": "...", ...}). Same content, so turn it into the list of "key: value" lines instead of rejecting the whole reply
    (a rejected reply costs ~28 s: the correction round trip drops the other fields and needs a third call)."""
    for k in keys:
        if isinstance(o.get(k), dict): o[k] = [f"{a}: {b}" for a, b in o[k].items()]


CHAR_CAP = 110       # most characters of one character's appearance line (the budget can make it shorter, see char_cap)
SCENE_MIN = 150      # characters a shot's own scene (action, setting, colors) must keep after the cast lines are added


def _norm_cast(an, n):
    """Makes the analyze answer's cast usable whatever the model returned: a list of {id, name, origin, role, main} with unique ids, shot_list entries with a list of known ids. No characters is a valid answer."""
    chars, seen = [], set()
    for c in (an.get("characters") if isinstance(an.get("characters"), list) else []):
        if isinstance(c, str): c = {"id": c, "name": c}
        if not isinstance(c, dict) or not _s(c, "name") and not _s(c, "id"): continue
        cid = re.sub(r"[^a-z0-9_]+", "_", str(c.get("id") or c["name"]).lower()).strip("_") or f"c{len(chars) + 1}"
        if cid in seen: continue
        seen.add(cid); chars.append({"id": cid, "name": str(c.get("name") or c["id"]).strip(), "origin": c.get("origin") if c.get("origin") in ("named", "implied", "invented") else "invented",
                                     "role": str(c.get("role") or "").strip(), "main": bool(c.get("main"))})
    if chars and not any(c["main"] for c in chars): chars[0]["main"] = True
    for sh in an.get("shot_list", [])[:n]:
        ids = sh.get("characters") if isinstance(sh.get("characters"), list) else []
        sh["characters"] = [re.sub(r"[^a-z0-9_]+", "_", str(i).lower()).strip("_") for i in ids]
        sh["characters"] = [i for i in dict.fromkeys(sh["characters"]) if i in seen] if chars else []
    an["characters"] = chars
    an["kind"] = an.get("kind") if an.get("kind") in ("explainer", "story", "mood") else "explainer"
    an["narration_voice"] = an["narration_voice"].strip() if _s(an, "narration_voice") else "a neutral narrator"
    return an


def char_cap(cfg, an, style_chars=None):
    """How long one character's appearance line may be: the most characters that share a shot split what is left of the prompt after the style line, the no-text clause and SCENE_MIN."""
    cap = cfg["limits"]["image_prompt_chars"]; clause = cfg["policy"].get("image_text", "")
    style = style_chars if style_chars is not None else int(cap * (cfg.get("director") or {}).get("style_share", 0.25))
    room = cap - style - 2 - (len(clause) + 2 if clause else 0) - SCENE_MIN
    together = max([len(x.get("characters", [])) for x in an.get("shot_list", [])] + [1])
    return max(40, min(CHAR_CAP, room // together - 12))                # 12 = the name label ("Harry: ") and the separator


def _trim_words(text, limit):
    text = " ".join(str(text).split())
    if len(text) <= limit: return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:- ")
    return cut or text[:limit]


def cast_line(cast, ids, room):
    """The words that describe the characters present in a shot, copied from the cast sheet so every picture says the same thing: "Name: appearance." for each, shortened evenly if they do not fit in `room`."""
    rows = [(c["name"], c["appearance"]) for i in ids for c in cast if c["id"] == i]
    if not rows: return ""
    def build(each): return " ".join(f"{n}: {_trim_words(a, each).rstrip('.')}." for n, a in rows)
    each = max(len(a) for _, a in rows)
    while len(build(each)) > room and each > 20: each -= 4
    return build(each)


def analyze(job, cfg, caps, p, req, res, n, sat):
    lim = cfg["limits"]
    for attempt in range(lim["max_research_queries"] + 1):
        def check(o):
            _as_list(o, "rules", "open_details")
            if o.get("characters") is not None and not isinstance(o.get("characters"), list): return "characters must be a list (empty when nobody recurs)"
            sl = o.get("shot_list", [])
            if len(sl) < n: return f"shot_list has {len(sl)} entries, need {n}"
            if not all(_s(x, "topic") and _s(x, "purpose") for x in sl[:n]): return "every shot_list entry needs topic and purpose"
            if not _s(o, "intent") or not _s(o, "title") or not isinstance(o.get("rules"), list) or not isinstance(o.get("open_details"), list): return "need intent, title, rules (list) and open_details (list)"
            return None
        try:
            o = llm.ask_json(cfg["llm"], "You are the director who plans a set of generated pictures before anything is drawn. First analyze what the request really needs.",
                f"Request: {req['query']}\nTone: {p['tone']}\nContent rules: {sat}\n\nMaterial:\n{_facts(res)}\n\n"
                f"Return JSON with these fields in this order: \"kind\" (\"explainer\" if the request explains something or shows facts, \"story\" if it tells a story or follows someone through events, \"mood\" for a single scene or atmosphere), "
                "\"intent\" (one sentence: what the viewer should understand or feel; for a story, its premise), \"audience\", "
                "\"characters\" (every person, animal or creature the pictures follow: [{\"id\": a short lowercase handle, \"name\": how they are called, \"origin\": \"named\" if the request names them or they are a well-known character, \"implied\" if it only refers to them (for example \"his girlfriend\": you choose who they are), \"invented\" if the story needs them, \"role\": a few words, \"main\": true for the lead}]; an empty list when nobody recurs, for example when the request explains a natural process or shows objects or places), "
                "\"rules\" (the facts and physical or spatial rules every picture must obey, each one short and checkable, taken from the material or from common knowledge; e.g. which way light travels, what is in front of or behind what), "
                "\"open_details\" (what a generic request leaves open that a picture needs: colors of key objects, positions, which way figures face, setting, time of day, lighting), "
                f"\"title\" (short title for the set), \"shot_list\" (exactly {n} different shots that together cover the request in a sensible order, each {{\"topic\": short subject, \"purpose\": the one idea this picture must convey, "
                "\"characters\": [the ids of the characters visible in this shot, empty when none]}}. For a story the shot_list is an arc (setup, rising tension, a turn, an ending) and the lead appears in most shots and does not vanish without a reason; "
                "for an explainer without characters every list is empty)" + (", \"narration_voice\" (who speaks the voice-over. When the request has someone talking to themselves, thinking aloud, addressing the viewer or telling their own story, write \"<character name>, in the first person\" and the lines are that character speaking; for every other request write \"a neutral narrator\")" if p.get("narrated") else "") + ".",
                temperature=0.5, max_tokens=4000, check=check)
            return _norm_cast(o, n)
        except llm.LLMError as e:
            if not p["needs_web"] or attempt >= lim["max_research_queries"]: raise
            job.log(f"not enough shots ({e}); asking the web for more (extra search {attempt + 1} of {lim['max_research_queries']})")
            r = research.ask(cfg["research"], f"{p['research_questions'][0]} Give {n} different items; the ones already known are in the earlier answers.")
            res.append({"question": "more", "text": r["text"], "secs": round(r["secs"], 1)})


def decide(cfg, req, p, an, res, log=None):
    style_cap = int(cfg["limits"]["image_prompt_chars"] * (cfg.get("director") or {}).get("style_share", 0.25)); style_words = style_cap // 10
    chars = an.get("characters") or []; cc = char_cap(cfg, an)
    def check(o):
        if not isinstance(o.get("decisions"), list) or not o["decisions"]: return "decisions must be a non-empty list"
        if chars:
            cast = o.get("cast")
            if not isinstance(cast, list) or {str(c.get("id")) for c in cast if isinstance(c, dict)} < {c["id"] for c in chars}: return "cast needs one entry for EVERY character id: " + ", ".join(c["id"] for c in chars)
            for c in cast:
                if not isinstance(c, dict) or not _s(c, "appearance"): return "every cast entry needs an appearance"
                if len(c["appearance"]) > cc * 1.3: return f"appearance of {c.get('id')} is {len(c['appearance'])} characters; at most {cc}, keep only what makes them recognizable"
        st = o.get("style")
        if not isinstance(st, dict) or not all(_s(st, k) for k in ("look", "palette", "lighting", "camera")): return "style needs look, palette, lighting and camera"
        return None
    o = llm.ask_json(cfg["llm"], "You are the director fixing every open detail before the pictures are drawn, so nothing is left for the picture model to guess.",
        f"Request: {req['query']}\nTone: {p['tone']}\nKind: {an.get('kind', 'explainer')}\nIntent: {an['intent']}\nRules every picture must obey: {json.dumps(an['rules'], ensure_ascii=False)}\nOpen details: {json.dumps(an['open_details'], ensure_ascii=False)}\n"
        + (f"Characters: {json.dumps(chars, ensure_ascii=False)}\n" if chars else "") + "\n"
        "Return JSON: {\"decisions\": [{\"detail\": ..., \"value\": a concrete choice (exact colors, positions, directions)}] for EVERY open detail, "
        "\"style\": (the four fields together at most " + str(style_words) + " words, no color codes) {\"look\": one phrase for a single consistent look for ALL pictures that fits the request and tone (photographic realism, a rendering technique, an illustration style: whatever fits), \"palette\": ..., \"lighting\": ..., \"camera\": ...}, "
        + ("\"cast\": [one entry per character: {\"id\": the character's id, \"appearance\": what they look like in EVERY picture, as one fixed phrase of at most " + str(cc) + " characters: age and build, face and hair, clothes with their colors, one distinctive detail; concrete and visual, in the look of the style; for a well-known character use their well-known features; characters who appear together must differ clearly in at least two visible traits such as hair color, clothing color, build or headwear}], " if chars else "")
        + "\"recurring\": [fixed appearance of every object that appears in more than one shot; empty if none]}", temperature=0.4, max_tokens=3000, check=check)
    o["style"] = fit_style(cfg, o["style"], style_cap, log)
    by_id = {str(c.get("id")): c for c in (o.get("cast") or []) if isinstance(c, dict)}
    o["cast"] = [{"id": c["id"], "name": c["name"], "origin": c["origin"], "role": c["role"], "main": c["main"],
                  "appearance": _trim_words((by_id.get(c["id"]) or {}).get("appearance") or c["role"] or c["name"], cc)} for c in chars]
    return o


SLACK = 1.1      # the video stage already speeds speech up (caps max_tempo), so a few characters over the budget are harmless; failing a whole job over them is not


def _shot_check(budget, scene_cap=None, motion=True, narration=True):
    def check(o):
        sc = o.get("scene")
        if not isinstance(sc, dict) or not all(_s(sc, k) for k in SCENE):
            miss = [k for k in SCENE if not (isinstance(sc, dict) and _s(sc, k))]
            return "scene needs non-empty " + ", ".join(SCENE) + f"; missing or empty: {', '.join(miss)}"
        if scene_cap and len(image_prompt(sc)) > scene_cap: return f"the scene is too long: the compiled picture description is {len(image_prompt(sc))} characters, the limit is {scene_cap}; rewrite every field as one short phrase"
        if not _s(o, "caption") or len(o["caption"]) > 160: return "caption needed, at most 160 characters"
        if motion and (not _s(o, "motion") or len(o["motion"]) > 300): return "motion needed, at most 300 characters"
        if narration and (not _s(o, "narration") or len(o["narration"]) > int(budget * SLACK)): return f"narration needed, at most {budget} characters (it is {len(o.get('narration') or '')})"
        return None
    return check


WEIGHT = {"subject": .50, "setting": .25, "colors": .25}     # share of the scene's character budget per field


LABELS = 25      # "Setting: ", "Colors: ", three full stops and two spaces added by image_prompt


def _weights(cfg):
    w = (cfg.get("director") or {}).get("scene_weights") or WEIGHT
    return w if set(w) == set(SCENE) else WEIGHT


def field_limits(scene_cap, weights=None):
    """Per-field character limits that add up to the scene budget (LABELS characters go to the labels and punctuation image_prompt adds). They guide the writer; only the total is enforced."""
    return {k: max(15, int((scene_cap - LABELS) * w)) for k, w in (weights or WEIGHT).items()}


DANGLING = re.compile(r"(?:\s+(?:in|on|at|of|to|from|with|and|or|the|a|an|by|for|as|into|onto|while|that|his|her|its|their))+$", re.I)


def _cut_phrase(text, n):
    """guard.cut, then drop the words a phrase cannot end on ("Harry stands motionless in" -> "Harry stands motionless")."""
    t = _cut(text, n); t2 = DANGLING.sub("", t).rstrip(" ,;:-")
    return t2 if len(t2) >= min(15, len(t)) else t


def _trim_longest(d, keys, measure, limit, floor=15, lim=None):
    """Last resort: shorten fields at a word boundary until measure(d) <= limit. Never raises. With `lim` (each field's own character limit) the fields that are over THEIR limit are cut to it first, so one long
    field does not eat the room of the field the picture depends on most; only then is the longest field shortened."""
    d = dict(d)
    if lim:
        for k in keys:
            if measure(d) <= limit: return d
            if len(d[k]) > max(floor, lim.get(k, 0)): d[k] = _cut_phrase(d[k], max(floor, lim[k]))
    for _ in range(40):
        excess = measure(d) - limit
        if excess <= 0: return d
        k = max((k for k in keys if len(d[k]) > floor), key=lambda k: len(d[k]), default=None)
        if k is None: return d
        d[k] = _cut_phrase(d[k], max(floor, len(d[k]) - excess))
    return d


def _changed(a, b, keys): return ", ".join(f"{k} {len(a[k])}->{len(b[k])}" for k in keys if a[k] != b[k])


def fit_scene(cfg, scene, lim, scene_cap, log=None, info=None):
    """Keep the compiled scene within its character budget (long picture prompts reset the 3090 box); the budget is what is left of the whole-prompt cap after the style line and the no-text clause. A scene that fits is
    accepted as written. Otherwise the writer rewrites it (only this shot), up to 3 rounds with more freedom each time, told the exact lengths. If it still does not fit, the longest fields are trimmed at a word
    boundary (logged). A job is never failed for length."""
    def measure(sc): return len(image_prompt(sc).rstrip(". "))
    def check(o): return None if isinstance(o, dict) and all(_s(o, k) for k in SCENE) else "need all the scene fields as non-empty text"
    for rnd, temp in enumerate((0.2, 0.5, 0.8), 1):
        n = measure(scene)
        if n <= scene_cap:
            if info is not None: info["method"] = "none" if rnd == 1 else "rewrite"
            return scene
        over = {k: f"{len(scene[k])} -> at most {lim[k]}" for k in SCENE if len(scene[k]) > lim[k]} or {k: f"{len(scene[k])} -> at most {lim[k]}" for k in SCENE}
        try:
            o = llm.ask_json(cfg["llm"], "You shorten text without losing the key facts.",
                f"These picture-scene fields compile into a description of {n} characters, but it must be at most {scene_cap}. Rewrite ONLY the fields listed below so each is within its limit, and copy the other fields unchanged.\n"
                f"Keep every color, position, direction and the main subject; drop adjectives, repeated words and extra detail; every field must stay a complete phrase.\n"
                f"Fields: {json.dumps(scene, ensure_ascii=False)}\nFields that are too long (current length -> limit in characters): {json.dumps(over)}\n"
                "Return JSON with the same keys.", temperature=temp, max_tokens=1500, check=check)
        except llm.LLMError:
            break
        new = {k: o[k] for k in SCENE}
        if info is not None: info["rewrites"] = rnd
        if log: log(f"  scene rewrite {rnd}: {n} -> {measure(new)} characters (budget {scene_cap})")
        scene = new
    cut = _trim_longest(scene, SCENE, measure, scene_cap, lim=lim)
    if info is not None: info["method"] = "trim" if cut != scene else ("rewrite" if info.get("rewrites") else "none")
    if log and cut != scene: log("  scene trimmed at a word boundary to fit the cap: " + _changed(scene, cut, SCENE))
    return cut


STYLE = ("look", "palette", "lighting", "camera")


def fit_style(cfg, st, style_cap, log=None):
    """The style line is shared by every picture. One rewrite if it is over 115% of its share, then a word-boundary trim of the longest field; never raises."""
    hard = int(style_cap * 1.15)
    def measure(s): return len(style_line(s))
    if measure(st) > hard:
        try:
            o = llm.ask_json(cfg["llm"], "You shorten text without losing the key facts.",
                f"Shorten these four style fields so that together they are at most {style_cap} characters (now {measure(st)}). Keep the overall look; each stays a short phrase, no color codes.\nFields: {json.dumps({k: st[k] for k in STYLE}, ensure_ascii=False)}\nReturn JSON with the same four keys.",
                temperature=0.3, max_tokens=800, check=lambda o: None if isinstance(o, dict) and all(_s(o, k) for k in STYLE) else "need all four fields as non-empty text")
            new = {**st, **{k: o[k] for k in STYLE}}
            if log: log(f"  style rewrite: {measure(st)} -> {measure(new)} characters (limit {hard})")
            st = new
        except llm.LLMError:
            pass
    cut = _trim_longest(st, STYLE, measure, hard)
    if log and cut != st: log("  style trimmed at a word boundary: " + _changed(st, cut, STYLE))
    return cut


SHOT_HEAD = ("The scene's fields are compiled into ONE picture description that must stay under {scene_cap} characters in total, so every field is limited in characters: {field_limits}. Write each as one short phrase (no color codes). Return JSON with these fields in this order: \"rules_applied\" (which of the rules apply to this shot and how the scene obeys them), "
             "\"scene\": {\"subject\": who or what is shown and what it is doing; say where the key things sit and which way people face only when that matters to the idea, \"setting\": where, with the framing or camera angle, \"colors\": the colors of the key objects and the light}, "
             "\"caption\" (one line in the requested tone, under 160 characters, no hashtags)")
SHOT_MOTION = ", \"motion\" (ONE or TWO sentences for an image-to-video model: what moves and how the camera moves, gentle and physically plausible; do not re-describe the picture)"
SHOT_NARRATION = ", \"narration\" (what the narrator says over this picture; at most {budget} characters; spoken language; no stage directions)"


def shot_format(video=True, narrated=True):
    """The fields a shot needs: always scene and caption; a motion line only for a video; a narration line only for a narrated video."""
    return SHOT_HEAD + (SHOT_MOTION if video else "") + (SHOT_NARRATION if narrated else "") + "."


SHOT_FORMAT = shot_format()


def prompt_budget(cfg, dec):
    """How the whole-prompt cap is spent: style line + no-text clause + scene (same assembly as pipeline.images: scene, style, clause), and the per-field limits of the scene."""
    clause = cfg["policy"].get("image_text", ""); style = len(style_line(dec["style"]))
    scene_cap = cfg["limits"]["image_prompt_chars"] - style - 2 - (len(clause) + 2 if clause else 0)
    if scene_cap < 200: raise llm.LLMError(f"only {scene_cap} characters are left for the scene after the style line and the no-text clause; raise [limits] image_prompt_chars")
    return {"cap": cfg["limits"]["image_prompt_chars"], "style_chars": style, "clause_chars": len(clause), "scene_cap": scene_cap, "limits": field_limits(scene_cap, _weights(cfg))}


def shots(cfg, caps, req, p, an, dec, res, n, sat, log=None, feed=None):
    budget = video.narration_budget(caps); out = []; bud = prompt_budget(cfg, dec); scene_cap, lim = bud["scene_cap"], bud["limits"]
    is_video = bool(req.get("video")); narrated = is_video and p.get("narrated", True); fmt = shot_format(is_video, narrated)
    cast = dec.get("cast") or []; names = {c["id"]: c["name"] for c in cast}; story = an.get("kind") == "story"; voice = an.get("narration_voice", "a neutral narrator")
    ctx = (f"Request: {req['query']}\nTone: {p['tone']}\nContent rules: {sat}\nIntent: {an['intent']}\nRules every picture must obey: {json.dumps(an['rules'], ensure_ascii=False)}\n"
           f"Decisions already made: {json.dumps(dec['decisions'], ensure_ascii=False)}\nStyle bible: {json.dumps(dec['style'], ensure_ascii=False)}\nRecurring elements: {json.dumps(dec.get('recurring', []), ensure_ascii=False)}\n"
           + (f"Kind of piece: {an.get('kind', 'explainer')}\nCast (their looks are added to every picture description automatically): {json.dumps([{k: c[k] for k in ('id', 'name', 'role', 'appearance')} for c in cast], ensure_ascii=False)}\n" if cast else "")
           + f"Material:\n{_facts(res)}\n")
    for k, sh in enumerate(an["shot_list"][:n], 1):
        t_shot = time.time()
        ids = [i for i in sh.get("characters", []) if i in names]
        line = cast_line(cast, ids, max(0, scene_cap - SCENE_MIN)); scene_cap_k = scene_cap - (len(line) + 1 if line else 0); lim_k = field_limits(scene_cap_k, _weights(cfg))
        lim_txt = ", ".join(f"{k2} {v}" for k2, v in lim_k.items())
        prev = "\n".join(f"  {j}. {x['topic']}" + (f" [{', '.join(names.get(i, i) for i in x['characters'])}]" if x.get("characters") else "") + f": {x['scene']['subject']}" + (f" | narration: {x['narration']}" if x.get('narration') else "") for j, x in enumerate(out, 1)) or "  (this is the first shot)"
        who = (f"Characters in this shot: {', '.join(names[i] for i in ids)}. Their looks are added to the picture description automatically, so refer to them by name only and say what each one does, where they stand and which way they face (keep their places consistent with the previous shot); never describe their faces or clothes again. " if ids
               else ("No character is visible in this shot. " if cast else ""))
        o = llm.ask_json(cfg["llm"], "You are the director writing the full specification of ONE shot of a narrated picture set.",
            f"{ctx}\nShots so far:\n{prev}\n\nNow shot {k} of {n}: topic \"{sh['topic']}\", purpose: {sh['purpose']}\n{who}"
            f"" + ((f"The narration is spoken by {voice} and continues the {'story' if story else 'explanation'} from the earlier shots without repeating their openings. ") if narrated else "") + fmt.replace("{budget}", str(budget)).replace("{scene_cap}", str(scene_cap_k)).replace("{field_limits}", lim_txt), temperature=0.5, max_tokens=2500, check=_shot_check(budget, None, is_video, narrated))
        raw, info = dict(o["scene"]), {}
        o["scene"] = fit_scene(cfg, o["scene"], lim_k, scene_cap_k, (lambda m, k=k: log(f"  shot {k}: {m.strip()}")) if log else None, info)
        out.append({"topic": sh["topic"], "purpose": sh["purpose"], **{k2: o[k2] for k2 in ("rules_applied", "scene", "caption", "motion", "narration") if k2 in o},
                    **({"characters": ids, "cast_line": line} if cast else {}), "fit": info.get("method", "none"), **({"scene_raw": raw} if o["scene"] != raw else {})})
        out[-1]["secs"] = round(time.time() - t_shot, 1); progress.update(shots_done=k, shots_total=n)
        if feed: feed(("shot", {"topic": out[-1]["topic"], "caption": out[-1]["caption"], "image_prompt": image_prompt(out[-1]["scene"], out[-1].get("cast_line", ""))}))          # the picture can be drawn now
    return out


def image_prompt(scene, cast_line=""):
    """Compile a scene spec into one picture description: the cast sheet's words for the characters present (identical in every shot), then every field the director fixed, in a stable order."""
    scene = {k: LABEL.sub("", HEX.sub("", v)) for k, v in scene.items()}      # the picture model needs plain words: no hex codes, no leaked shot labels
    parts = [scene["subject"].strip().rstrip(".") + ".", f"Setting: {scene['setting'].strip().rstrip('.')}.", f"Colors: {scene['colors'].strip().rstrip('.')}."]
    return " ".join(([cast_line] if cast_line else []) + parts)


def style_line(st): return HEX.sub("", ", ".join(st[k].strip().rstrip(".") for k in ("look", "palette", "lighting", "camera")))


def direct(job, cfg, caps, feed=None):
    try: return _direct(job, cfg, caps, feed)
    except Exception as e:                                                        # noqa: BLE001
        if feed: feed(("error", str(e)))                                         # never leave the picture stage waiting for shots that will not come
        raise


def _direct(job, cfg, caps, feed):
    from . import pipeline
    p, req = job.read("plan.json"), job.state["request"]; res = job.read("research.json"); n = p["count"]; sat = pipeline.policy_text(cfg)
    an = analyze(job, cfg, caps, p, req, res, n, sat); job.log(f"  analyzed: {an['kind']}, {len(an['rules'])} rules, {len(an['open_details'])} open details, " + (f"cast: {', '.join(c['name'] + ' (' + c['origin'] + ')' for c in an['characters'])}" if an["characters"] else "no characters"))
    dec = decide(cfg, req, p, an, res, job.log); job.log(f"  decided {len(dec['decisions'])} details; style: {dec['style']['look'][:70]}")
    for c in dec["cast"]: job.log(f"  cast {c['name']}: {c['appearance']}")
    if feed: feed(("style", style_line(dec["style"])))
    sh = shots(cfg, caps, req, p, an, dec, res, n, sat, job.log, feed); job.log(f"  wrote {len(sh)} shot specs (shot calls averaged {sum(x['secs'] for x in sh) / max(1, len(sh)):.1f}s)")
    (job.dir / "director").mkdir(exist_ok=True)                       # every step's output, for debugging: what each call produced, before the next step touched it
    job.write("director/01_analyze.json", an); job.write("director/02_decide.json", dec); job.write("director/03_budget.json", prompt_budget(cfg, dec)); job.write("director/04_shots.json", sh)
    job.write("research.json", res)
    job.write("direction.json", {"title": an["title"], "intent": an["intent"], "audience": an.get("audience"), "rules": an["rules"], "open_details": an["open_details"], "decisions": dec["decisions"],
                                 "style": dec["style"], "style_line": style_line(dec["style"]), "recurring": dec.get("recurring", []), "kind": an["kind"], "narration_voice": an["narration_voice"], "cast": dec["cast"], "shots": sh})
    job.write("items.json", {"title": an["title"], "cast": [{k: c[k] for k in ("id", "name", "origin", "role", "appearance")} for c in dec["cast"]],
                             "items": [{"topic": x["topic"], "caption": x["caption"], "image_prompt": image_prompt(x["scene"], x.get("cast_line", "")), **({"characters": x["characters"]} if x.get("characters") is not None and dec["cast"] else {})} for x in sh]})
    if feed: feed(("end",))
