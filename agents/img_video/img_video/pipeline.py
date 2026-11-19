"""Image-set pipeline: plan -> research -> items -> images -> result. Each stage is resumable (see jobs.py). The agent returns file paths and captions; delivering them (Telegram, etc.) is the caller's job.
Nothing here is specific to a topic: the query decides the number of pictures, whether the web is needed, the tone and the style."""
import queue
import threading
import time
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor

from . import comfy, config, director, guard, llm, local_sd, progress, research, verify, video
from .jobs import Job, fingerprint

V = {"plan": 6, "research": 2, "direct": 6, "images": 11}     # per-stage prompt version: bump when that stage's prompt or logic changes so old results are not reused


def policy_text(cfg):
    """The picture-description rule for real people, chosen by [policy] real_people (allow | alter). Shapes prompts only; nothing is refused."""
    pol = cfg["policy"]; return pol[pol["real_people"]]


def _today(): return time.strftime("%B %d, %Y")


NARRATED_FIELD = (", \"narrated\": true if the video should have a voice-over narration (an explanation, a lesson, a story or a news summary, or the request asks for narration, a voice or commentary), "
                  "false for a purely visual video (a clip, an animation, a mood piece) with no spoken part")


SECONDS_FIELD = (", \"seconds\": the length of the video in seconds if the request states one (\"2 minutes\" is 120, \"a minute and a half\" is 90, \"30 seconds\" is 30), otherwise null")


def plan(job, cfg, caps):
    req = job.state["request"]; lim = cfg["limits"]

    def check(o):
        n = o.get("count")
        if not isinstance(n, int) or not 1 <= n <= lim["max_images"]: return f"count must be an integer from 1 to {lim['max_images']}"
        if req.get("video") and o.get("seconds") is not None and (isinstance(o["seconds"], bool) or not isinstance(o["seconds"], (int, float)) or o["seconds"] <= 0): return "seconds must be a positive number or null"
        if o.get("needs_web") and not o.get("research_questions"): return "needs_web is true but research_questions is empty"
        if not isinstance(o.get("visual_style"), str) or not o["visual_style"].strip(): return "visual_style must be a non-empty phrase"
        return None
    o = llm.ask_json(cfg["llm"], "You plan how to fulfil a request for a set of generated pictures.",
        f"Today's date: {_today()}\nRequest: {req['query']}\n\nReturn JSON: {{\"count\": number of pictures requested (use {req.get('count') or 'the number in the request, or 6 if none is stated'}), "
        "\"needs_web\": true if the request depends on current events or facts that must be looked up on the web, otherwise false, "
        "\"research_questions\": [complete instructions to a web researcher, including today's date when current news is involved. Each must ask ONLY for facts to look up (never for creative work such as choosing visuals or writing captions); usually one is enough; empty if needs_web is false], "
        "\"tone\": \"the tone asked for, in a few words\", \"visual_style\": \"one phrase describing a single consistent look for ALL the pictures that fits the request and tone (photographic realism, a rendering technique, an illustration style: whatever the request calls for)\"" + (NARRATED_FIELD + SECONDS_FIELD) * bool(req.get("video")) + "}", check=check)
    o["narrated"] = bool(req.get("video")) and (o["narrated"] if isinstance(o.get("narrated"), bool) else False)      # only a video can be narrated; the planner decides, a missing answer means silent
    if req.get("video") and isinstance(o.get("seconds"), (int, float)):                          # the request states a length: the number of shots follows from it. A count passed by the chat model does not override it (the model fills one in even when the user gave none)
        n = min(video.shots_for_seconds(caps, o["seconds"]), lim["max_images"])
        job.log(f"  the request asks for {o['seconds']:g} s: {n} shots" + (f" (ignoring a count of {req['count']} passed with the request)" if req.get("count") and req["count"] != n else "")); o["count"] = n
    elif req.get("count"): o["count"] = req["count"]
    if req.get("video"):                                                                       # a video has a length limit: cut the number of shots to fit it
        most = video.max_shots(cfg, caps, o["narrated"])
        if o["count"] > most: job.log(f"  video length limit: {o['count']} shots -> {most} (at most {cfg['limits']['max_video_seconds']} s)"); o["count"] = most
    job.write("plan.json", o)


def do_research(job, cfg, caps):
    p = job.read("plan.json"); out = []
    given = job.state["request"].get("research_text")
    if given:                                                  # research supplied with the request: no gateway call
        job.log(f"using the research text supplied with the request ({len(given)} chars); no gateway call")
        job.write("research.json", [{"question": "(supplied with the request)", "text": given, "secs": 0.0}]); return
    if p["needs_web"]:
        for q in p["research_questions"][:cfg["limits"]["max_research_queries"]]:
            job.log(f"researching: {q[:110]}")
            try:
                r = research.ask(cfg["research"], q)
            except research.ResearchError as e:
                job.log(f"  skipped this question: {e}"); continue
            out.append({"question": q, "text": r["text"], "secs": round(r["secs"], 1)})
            job.log(f"  answer in {r['secs']:.0f}s ({len(r['text'])} chars)")
        if not out: raise research.ResearchError("no web research succeeded, and the request needs it")
    job.write("research.json", out)


class ListSource:
    """The shots of a finished director stage, read from the job folder."""
    def __init__(self, job): self.d = job.read("items.json"); self.style = job.read("direction.json")["style_line"]
    def first(self): return bool(self.d["items"])
    def items(self): yield from enumerate(self.d["items"], 1)


class FeedSource:
    """The shots of a director that is still writing: each arrives (put) as soon as it is final, so pictures can be drawn while the next shot is being written. Messages: ("style", line), ("shot", item), ("end",), ("error", text)."""
    def __init__(self): self.q = queue.Queue(); self.style = None; self._first = None
    def put(self, msg): self.q.put(msg)
    def _take(self):
        msg = self.q.get()
        if msg[0] == "error": raise RuntimeError("the director failed: " + str(msg[1])[:300])
        return msg
    def first(self):
        """Wait until the style and the first shot exist (the 3090 is not needed before that)."""
        while True:
            msg = self._take()
            if msg[0] == "style": self.style = msg[1]
            elif msg[0] == "shot": self._first = msg[1]; return True
            elif msg[0] == "end": return False
    def items(self):
        k = 1; yield k, self._first
        while True:
            msg = self._take()
            if msg[0] == "end": return
            if msg[0] == "shot": k += 1; yield k, msg[1]


def picture_size(cfg, caps, req):
    """Size the pictures are drawn at. A picture SET or single image always uses the full aspect size. A VIDEO only needs about [pipeline] video_picture_scale x the Wan input
    (the clip model shrinks the picture anyway), rounded to a multiple of 16 and never above the full size; 0 (default) = full size for video too."""
    w, h = caps["aspect"][req["aspect"]]
    k = float((cfg.get("pipeline") or {}).get("video_picture_scale", 0) or 0)
    if not (req.get("video") and k > 0): return w, h
    ww, wh = caps["video"]["sizes"][req["aspect"]]["wan"]
    r16 = lambda x: max(256, int(round(x * k / 16)) * 16)
    return min(w, r16(ww)), min(h, r16(wh))


def images(job, cfg, caps, source=None):
    """Draw the pictures; returns the seconds the 3090 spent rendering. The 3090 lock is taken only once the first shot is ready."""
    source = source or ListSource(job)
    if not source.first(): return 0.0
    with guard.gpu_lock(log=job.log): return _images(job, cfg, caps, source)


def _images(job, cfg, caps, source):
    n, req, style = job.read("plan.json")["count"], job.state["request"], source.style
    w, h = picture_size(cfg, caps, req); base = cfg["comfy"]["url"]; local = cfg["image"]["backend"] == "qwen-image-local"
    if local: local_sd.preflight(cfg["local"])
    else: comfy.preflight(base, cfg["comfy"]); comfy.wait_until_free(base, log=job.log)
    (job.dir / "images").mkdir(exist_ok=True); ver = cfg["verify"]; report = {}; render = 0.0
    for i, x in source.items():
        cur, tries = x["image_prompt"], []
        for attempt in range(1 + (ver["retries"] if ver["enabled"] else 0)):
            prompt = f"{cur.rstrip('. ')}, {style}" + (f", {cfg['policy']['image_text']}" if cfg["policy"].get("image_text") else "")
            seed = int(fingerprint([job.id, i] if attempt == 0 else [job.id, i, attempt]), 16) % 2**31
            png, secs = local_sd.generate_image(cfg["local"], prompt, w, h, seed, job.log) if local else comfy.generate_image(base, cfg["comfy"], prompt, w, h, seed)
            render += secs
            (job.dir / "images" / f"{i:02d}.png").write_bytes(png); job.log(f"  image {i}/{n} in {secs:.1f}s: {x['topic'][:70]}" + (f" (attempt {attempt + 1})" if attempt else "")); progress.update(pictures_done=i, pictures_total=n)
            if not ver["enabled"]: break
            t0 = time.time(); ok, problems = verify.check(cfg["llm"], png, cur, x["caption"]); tries.append({"attempt": attempt + 1, "ok": ok, "problems": problems, "check_secs": round(time.time() - t0, 1)})
            job.log(f"    check {i}: " + ("matches" if ok else "; ".join(problems)[:200]))
            if ok or attempt == ver["retries"]: break
            cur = verify.fix_prompt(cfg["llm"], cur, x["caption"], problems)
        report[str(i)] = tries
    job.write("verify.json", report)
    return render


def result(job, cfg, caps):
    d = job.read("items.json")
    vr = job.read("verify.json") if (job.dir / "verify.json").exists() else {}
    out = {"title": d["title"], **({"cast": d["cast"]} if d.get("cast") else {}), "images": [{"index": i, "path": str(job.dir / "images" / f"{i:02d}.png"), "topic": x["topic"], "caption": x["caption"],
                                            **({"check": {"attempts": len(vr[str(i)]), "ok": vr[str(i)][-1]["ok"], "problems": vr[str(i)][-1]["problems"]}} if vr.get(str(i)) else {})} for i, x in enumerate(d["items"], 1)],
           "stage_seconds": {k: v.get("secs") for k, v in job.state["stages"].items()}}
    job.write("result.json", out)


STAGES = ["plan", "research", "direct", "images", "result", "storyboard", "voice", "clips", "video"]
VIDEO_V = {"storyboard": 1, "voice": 1, "clips": 1, "video": 3}


def run(job, cfg, caps, stop_after=None, with_video=False):
    req = job.state["request"]; llm_id = cfg["llm"]["model"]; lock = job.lock(); job.state["status"] = "running"; job.save()
    try:
        _stages(job, cfg, caps, req, llm_id, stop_after)
        if with_video and stop_after in (None, "storyboard", "voice", "clips", "video"): _video_stages(job, cfg, caps, req, llm_id, stop_after)
        job.state["status"] = "done" if stop_after is None else f"stopped after {stop_after}"; job.save()
    except Exception:
        job.state["status"] = "failed"; job.save(); raise
    finally:
        lock.close()


def _direct_inputs(base, job, cfg, caps, req, pl):
    return dict(base, v=V["direct"], video=bool(req.get("video")), plan=pl, research=fingerprint(job.read("research.json")), policy=policy_text(cfg), budget=video.narration_budget(caps),
                cap=cfg["limits"]["image_prompt_chars"], image_text=cfg["policy"].get("image_text", ""), director=cfg.get("director", {}))


def _images_inputs(base, cfg, req, items, style, caps=None):
    return dict(base, v=V["images"], items=items, aspect=req["aspect"], style=style, comfy=cfg["comfy"], image=cfg["image"], local=cfg["local"], verify=cfg["verify"], image_text=cfg["policy"].get("image_text", ""),
                **({"video_size": picture_size(cfg, caps, req)} if (req.get("video") and caps) else {}))


def _stage_done(job, name, inputs, outputs):
    st = job.state["stages"].get(name, {})
    return st.get("status") == "done" and st.get("fp") == fingerprint(inputs) and all((job.dir / o).exists() for o in outputs)


def should_stream(cfg, job, stop_after, direct_inputs):
    """Draw pictures while the director is still writing the next shots: only when the pictures are drawn on the 3090 (this machine's GPU would then compete with the writer), when a picture stage follows,
    and when the director has to run anyway (a finished director is simply read back, as before)."""
    return (stop_after not in ("plan", "research", "direct") and cfg["image"]["backend"] == "comfy" and bool((cfg.get("pipeline") or {}).get("stream_pictures", True))
            and not _stage_done(job, "direct", direct_inputs, ["items.json", "direction.json"]))


def _direct_and_images_streaming(job, cfg, caps, req, base, dir_in):
    t0 = time.time(); src = FeedSource(); render = 0.0
    job.state["stages"]["images"] = {"status": "running", "fp": "streaming"}; job.save(); progress.stage("images", "running"); job.log("stage images: running (streaming: pictures are drawn while the director is still writing)")
    err = None
    with ThreadPoolExecutor(1) as ex:
        fd = ex.submit(job.run_stage, "direct", dir_in, lambda: director.direct(job, cfg, caps, feed=src.put), ["items.json", "direction.json"])
        try: render = images(job, cfg, caps, src)
        except Exception as e: err = e                                              # noqa: BLE001
        try: fd.result()                                                            # the director's own error wins over the picture stage's
        except Exception:
            job.state["stages"]["images"] = {"status": "failed", "fp": "streaming", "error": "the director failed"}; job.save(); raise
    if err:
        job.state["stages"]["images"] = {"status": "failed", "fp": "streaming", "error": str(err)[:300]}; job.state["status"] = "failed"; job.save(); raise err
    it = job.read("items.json"); fp = fingerprint(_images_inputs(base, cfg, req, it, job.read("direction.json")["style_line"], caps))       # the same fingerprint the sequential path computes, so a resume reuses the pictures
    wall = time.time() - t0; d = job.state["stages"]["direct"].get("secs", 0)
    job.state["stages"]["images"] = {"status": "done", "fp": fp, "secs": round(wall, 1), "render_secs": round(render, 1), "streamed": True}; job.save(); progress.stage("images", "done")
    job.log(f"stage images: done in {wall:.1f}s (streamed with the director: director {d}s + pictures {render:.1f}s = {d + render:.1f}s if run one after the other)")


def _warm_pictures(job, cfg):
    """Load the picture model on the 3090 in the background while the research and the director run (the box is idle then). Best effort: if the GPU lock is taken, ComfyUI is busy or anything fails, it is skipped
    and the first picture simply pays the load as before. Takes the same GPU lock as the picture stage for the few seconds it runs, so the two never overlap."""
    def go():
        try:
            with guard.gpu_lock(wait_s=0, log=job.log):
                t = comfy.warm(cfg["comfy"]["url"], cfg["comfy"], job.log)
            if t is not None: job.log(f"  picture model loaded in {t:.0f}s (warm-up while the research and the director run)")
        except Exception as e:                                                      # noqa: BLE001
            job.log(f"  picture model warm-up skipped: {str(e)[:120]}")
    threading.Thread(target=go, daemon=True, name="warm-pictures").start()


def should_warm(cfg, job, stop_after):
    return (stop_after not in ("plan", "research", "direct") and cfg["image"]["backend"] == "comfy" and bool((cfg.get("pipeline") or {}).get("warm_pictures", False))
            and job.state["stages"].get("images", {}).get("status") != "done")


def _stages(job, cfg, caps, req, llm_id, stop_after):
    base = {"llm": llm_id}
    plan_in = dict(base, v=V["plan"], query=req["query"], count=req.get("count"), video=bool(req.get("video")), day=_today())
    job.run_stage("plan", plan_in, lambda: plan(job, cfg, caps), ["plan.json"])
    if stop_after == "plan": return
    pl = job.read("plan.json")
    if should_warm(cfg, job, stop_after): _warm_pictures(job, cfg)
    job.run_stage("research", dict(base, v=V["research"], needs_web=pl["needs_web"], questions=pl["research_questions"], provider=cfg["research"]["provider"], supplied=fingerprint(req.get("research_text", ""))), lambda: do_research(job, cfg, caps), ["research.json"])
    if stop_after == "research": return
    dir_in = _direct_inputs(base, job, cfg, caps, req, pl)
    if should_stream(cfg, job, stop_after, dir_in):
        _direct_and_images_streaming(job, cfg, caps, req, base, dir_in)
        it = job.read("items.json")
    else:
        job.run_stage("direct", dir_in, lambda: director.direct(job, cfg, caps), ["items.json", "direction.json"])
        if stop_after == "direct": return
        it = job.read("items.json")
        job.run_stage("images", _images_inputs(base, cfg, req, it, job.read("direction.json")["style_line"], caps), lambda: images(job, cfg, caps), [f"images/{i:02d}.png" for i in range(1, len(it["items"]) + 1)])
    if stop_after == "images": return
    job.run_stage("result", dict(base, v=1, items=it), lambda: result(job, cfg, caps), ["result.json"])


def _video_stages(job, cfg, caps, req, llm_id, stop_after):
    """storyboard -> (voice on this machine's CPU, in a thread) || (clips on the 3090) -> video. Each stage is resumable by input fingerprint like the image stages."""
    base = {"llm": llm_id}; imgs = job.state["stages"]["images"]["fp"]; vd = video.vdir(job)
    job.run_stage("storyboard", dict(base, v=VIDEO_V["storyboard"], narrated=job.read("plan.json").get("narrated", True), images=imgs, items=fingerprint(job.read("direction.json")), budget=video.narration_budget(caps), sizes=caps["video"]["sizes"][req["aspect"]]),
                  lambda: video.storyboard(job, cfg, caps), ["video/storyboard.json"])
    if stop_after == "storyboard": return
    sb = job.read("video/storyboard.json"); ids = [s["i"] for s in sb["shots"]]; narrated = sb.get("narrated", True)
    vin = dict(v=VIDEO_V["voice"], narration=[s.get("narration", "") for s in sb["shots"]], voice=cfg["voice"])
    cin = dict(v=VIDEO_V["clips"], shots=[(s["i"], s["motion"]) for s in sb["shots"]], images=imgs, wan=cfg["wan"], size=sb["wan"], frames=caps["video"]["frames"])
    with ThreadPoolExecutor(1) as ex:
        fv = ex.submit(job.run_stage, "voice", vin, lambda: video.voice(job, cfg, caps), [f"video/say{i}.wav" for i in ids]) if narrated else None       # a silent video has no voice stage
        try:
            if stop_after != "voice": job.run_stage("clips", cin, lambda: video.clips(job, cfg, caps), [f"video/clip{i}.mp4" for i in ids])
        finally:
            if fv: fv.result()
    if stop_after in ("voice", "clips"): return
    job.run_stage("video", dict(v=VIDEO_V["video"], clips=job.state["stages"]["clips"]["fp"], voice=job.state["stages"]["voice"]["fp"] if narrated else None, video=caps["video"], padding=caps["padding"]),
                  lambda: video.assemble(job, cfg, caps), ["video/video.mp4", "video.json"])
