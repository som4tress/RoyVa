"""Wan 2.2 14B image-to-video on the ComfyUI box, standard library only. Two-job batch: job A loads only the high-noise expert and saves every shot's half-denoised latent; the latents are
moved to the server's input folder; job B loads only the low-noise expert, finishes every shot and saves the mp4s. Each 14B expert is read from disk once and RAM never holds both.
Never calls /free (host-RAM OOM at the container cap); refuses to start while somebody else's job is on the shared box."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import comfy, guard, wsprobe

MAX_FILE = 300_000_000


def _fetch(base, path, timeout=120):
    def go():
        with urllib.request.urlopen(urllib.request.Request(base.rstrip("/") + path), timeout=timeout) as r:
            return r.read(MAX_FILE + 1)
    return comfy.retrying(go)


def upload(base, data: bytes, name: str):
    """Put a file into the server's input folder (a picture, or a saved latent)."""
    bd = uuid.uuid4().hex
    body = (f'--{bd}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + data + \
           (f'\r\n--{bd}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n--{bd}--\r\n').encode()
    req = urllib.request.Request(base.rstrip("/") + "/upload/image", data=body, headers={"Content-Type": f"multipart/form-data; boundary={bd}"})
    try:
        def go():
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read()).get("name", name)
        return comfy.retrying(go)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise comfy.ComfyError(f"upload of {name} failed: {e}")


def _loaders(w, expert, width, height):
    """Loaders for ONE expert: only that expert's model and LoRA are loaded."""
    lora = w["lora_hi"] if expert == "hi" else w["lora_lo"]
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": w[expert], "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": w["clip"], "type": "wan", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": w["vae"]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": w["negative"]}},
        "20": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": lora, "strength_model": 1.0}},
        "9": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["20", 0], "shift": w["shift"]}},
    }


def _shot(wf, k, sh, width, height, frames):
    enc, img, i2v = str(1000 + k), str(1100 + k), str(1200 + k)
    wf[enc] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": sh["prompt"]}}
    wf[img] = {"class_type": "LoadImage", "inputs": {"image": sh["image_name"]}}
    wf[i2v] = {"class_type": "WanImageToVideo", "inputs": {"positive": [enc, 0], "negative": ["5", 0], "vae": ["4", 0], "width": width, "height": height, "length": frames, "batch_size": 1, "start_image": [img, 0]}}
    return i2v


def hi_workflow(w, shots, width, height, frames):
    wf = _loaders(w, "hi", width, height); steps = w["steps"]; half = steps // 2
    for k, sh in enumerate(shots):
        i2v = _shot(wf, k, sh, width, height, frames)
        wf[str(2000 + k)] = {"class_type": "KSamplerAdvanced", "inputs": {"model": ["9", 0], "add_noise": "enable", "noise_seed": sh["seed"], "steps": steps, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
                             "positive": [i2v, 0], "negative": [i2v, 1], "latent_image": [i2v, 2], "start_at_step": 0, "end_at_step": half, "return_with_leftover_noise": "enable"}}
        wf[str(2200 + k)] = {"class_type": "SaveLatent", "inputs": {"samples": [str(2000 + k), 0], "filename_prefix": "latents/img_video_hi"}}
    return wf


def lo_workflow(w, shots, latent_names, width, height, frames, fps):
    wf = _loaders(w, "lo", width, height); steps = w["steps"]; half = steps // 2
    for k, sh in enumerate(shots):
        i2v = _shot(wf, k, sh, width, height, frames)
        wf[str(2100 + k)] = {"class_type": "LoadLatent", "inputs": {"latent": latent_names[k]}}
        wf[str(3000 + k)] = {"class_type": "KSamplerAdvanced", "inputs": {"model": ["9", 0], "add_noise": "disable", "noise_seed": 0, "steps": steps, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
                             "positive": [i2v, 0], "negative": [i2v, 1], "latent_image": [str(2100 + k), 0], "start_at_step": half, "end_at_step": 10000, "return_with_leftover_noise": "disable"}}
        wf[str(4000 + k)] = {"class_type": "VAEDecode", "inputs": {"samples": [str(3000 + k), 0], "vae": ["4", 0]}}
        wf[str(4100 + k)] = {"class_type": "CreateVideo", "inputs": {"images": [str(4000 + k), 0], "fps": float(fps)}}
        wf[str(4200 + k)] = {"class_type": "SaveVideo", "inputs": {"video": [str(4100 + k), 0], "filename_prefix": "img_video_clip", "format": "mp4", "codec": "h264"}}
    return wf


def run_multi(base, wf, timeout, poll=2.0, prof=None):
    """Submit one graph; returns {node_id: bytes} for every saved video and {node_id: bytes} for every saved latent.
    If `prof` is a dict it is filled with per-node timing (wsprobe.summarize) read from the job's websocket events: read-only and best-effort, it never changes the job."""
    t0 = time.time(); probe = wsprobe.Probe(base).start() if prof is not None else None
    try:
        guard.trim_workflow(wf, comfy._hard(), log=lambda m: print(m, flush=True))      # the same 3090 ceiling as comfy._call: this client posts graphs itself
        body = {"prompt": wf, **({"client_id": probe.cid} if probe and probe.ok else {})}
        req = urllib.request.Request(base.rstrip("/") + "/prompt", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        pid = json.loads(comfy.retrying(lambda: urllib.request.urlopen(req, timeout=60).read()))["prompt_id"]
    except urllib.error.HTTPError as e:
        raise comfy.ComfyError(f"ComfyUI refused the graph (HTTP {e.code}): {e.read(600).decode('utf-8', 'replace')}")
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        if probe: probe.stop()
        raise comfy.ComfyError(f"could not submit to ComfyUI: {e}")
    while time.time() - t0 < timeout:
        time.sleep(poll)
        hist = json.loads(comfy._call(base, f"/history/{pid}")).get(pid)
        if not hist: continue
        st = hist.get("status", {})
        if st.get("status_str") == "error":
            msgs = [m for m in st.get("messages", []) if m and m[0] == "execution_error"]
            if probe: probe.stop()
            raise comfy.ComfyError("ComfyUI failed the job: " + str((msgs[0][1].get("exception_message") if msgs else "") or "unknown error")[:300])
        if not st.get("completed"): continue
        videos, latents = {}, {}
        for nid, node in hist.get("outputs", {}).items():
            for kind, bucket in (("latents", latents), ("images", videos)):
                for f in node.get(kind, []):
                    bucket[nid] = _fetch(base, "/view?" + urllib.parse.urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")}))
        if probe:
            time.sleep(0.3); probe.stop()
            try: prof.update(wsprobe.summarize(wf, probe.events, pid, t0, time.time()))
            except Exception:                                                      # noqa: BLE001  timing is optional
                pass
        return videos, latents
    if probe: probe.stop()
    raise comfy.ComfyError(f"ComfyUI did not finish within {timeout}s")


def animate(cfg, caps, shots, size, job_tag, out_for, log=lambda m: None):
    """shots = [{"i", "image" (png path), "motion"}]. Writes out_for(i) for each shot. Returns a dict of measured seconds (summed over the batches).
    The clips go to ComfyUI in batches of at most [wan] max_batch_clips (default 10, the size proven on this box): one batch holds every clip's latent and decoded video in memory, and a 4-clip batch already used about 22 of the
    container's 24 GiB. A batch is two ComfyUI jobs, A (high-noise expert) then B (low-noise expert), and each expert is read from disk (about 25 s) whenever the other one ran in between.
    With [wan] two_pass_batches the order is A1 A2 A3 then B1 B2 B3 instead of A1 B1 A2 B2 A3 B3: each expert is loaded once per video if ComfyUI keeps it between consecutive jobs. Every job still has at most max_batch_clips clips,
    so the memory use on the box is the same; the latents of the finished A jobs wait on THIS machine (a few MB per clip)."""
    size_n = max(1, int((cfg.get("wan") or {}).get("max_batch_clips", 10))); chunks = [shots[k:k + size_n] for k in range(0, len(shots), size_n)]
    if len(chunks) == 1: return _animate_batch(cfg, caps, shots, size, job_tag, out_for, log)
    two_pass = bool((cfg.get("wan") or {}).get("two_pass_batches", False))
    total = {}; t0 = time.time(); states = []
    def add(T):
        for k, v in T.items():
            if k not in ("total", "per_clip"): total[k] = round(total.get(k, 0) + v, 1)
    if two_pass:
        for n, chunk in enumerate(chunks, 1):
            log(f"clip batch {n} of {len(chunks)} ({len(chunk)} shots): high-noise pass"); states.append(_hi_pass(cfg, caps, chunk, size, f"{job_tag}b{n}", log))
        for n, st in enumerate(states, 1):
            log(f"clip batch {n} of {len(chunks)} ({len(st['shots'])} shots): low-noise pass"); _lo_pass(cfg, caps, st, size, out_for, log)
        for st in states: add(st["T"])
    else:
        for n, chunk in enumerate(chunks, 1):
            log(f"clip batch {n} of {len(chunks)} ({len(chunk)} shots)"); add(_animate_batch(cfg, caps, chunk, size, f"{job_tag}b{n}", out_for, log))
    total["batches"] = len(chunks); total["total"] = round(time.time() - t0, 1); total["per_clip"] = round(total["total"] / len(shots), 1)
    return total


def _animate_batch(cfg, caps, shots, size, job_tag, out_for, log):
    st = _hi_pass(cfg, caps, shots, size, job_tag, log); _lo_pass(cfg, caps, st, size, out_for, log)
    st["T"]["total"] = round(time.time() - st["t0"], 1); st["T"]["per_clip"] = round(st["T"]["total"] / len(shots), 1)
    return st["T"]


def _hi_pass(cfg, caps, shots, size, job_tag, log):
    """Uploads the stills and runs job A (high-noise expert) for these shots. Returns the state _lo_pass needs; the latents stay in memory."""
    base, w, v = cfg["comfy"]["url"], cfg["wan"], caps["video"]; width, height = size; frames = v["frames"]
    needed = [("UNETLoader", "unet_name", w["hi"]), ("UNETLoader", "unet_name", w["lo"]), ("CLIPLoader", "clip_name", w["clip"]), ("VAELoader", "vae_name", w["vae"]),
              ("LoraLoaderModelOnly", "lora_name", w["lora_hi"]), ("LoraLoaderModelOnly", "lora_name", w["lora_lo"])]
    missing = [f"{n}: {name}" for n, f, name in needed if name not in comfy._combo(base, n, f)]
    if missing: raise comfy.ComfyError("Wan model files not offered by the ComfyUI server: " + "; ".join(missing))
    comfy.wait_until_free(base, log=log)
    log(f"animating {len(shots)} shots at {width}x{height}, {w['steps']} steps: {w['hi']} / {w['lo']} / {w['clip']}")
    T = {}; t0 = time.time(); pool = ThreadPoolExecutor(6)
    names = list(pool.map(lambda s: upload(base, open(s["image"], "rb").read(), f"{job_tag}_still{s['i']}.png"), shots)); T["upload_images"] = round(time.time() - t0, 1)
    batch = [{"prompt": s["motion"], "image_name": n, "seed": 1000 + s["i"]} for s, n in zip(shots, names)]
    pa = {}; t = time.time(); _, lat = run_multi(base, hi_workflow(w, batch, width, height, frames), w["timeout"], prof=pa); T["job_a"] = round(time.time() - t, 1); log(wsprobe.describe("job A (high-noise)", pa))
    ids = [str(2200 + k) for k in range(len(shots))]
    if not all(i in lat for i in ids): raise comfy.ComfyError("the high-noise pass did not return every latent")
    return {"shots": shots, "batch": batch, "lat": [lat[i] for i in ids], "tag": job_tag, "T": T, "t0": t0}


def _lo_pass(cfg, caps, st, size, out_for, log):
    """Uploads the latents of _hi_pass and runs job B (low-noise expert); writes the clips."""
    base, w, v = cfg["comfy"]["url"], cfg["wan"], caps["video"]; width, height = size; frames, fps = v["frames"], v["wan_fps"]; shots, batch, T = st["shots"], st["batch"], st["T"]
    comfy.wait_until_free(base, log=log)
    pool = ThreadPoolExecutor(6)
    t = time.time(); lnames = list(pool.map(lambda k: upload(base, st["lat"][k], f"{st['tag']}_hi{k}.latent"), range(len(shots)))); T["upload_latents"] = round(time.time() - t, 1)
    pb = {}; t = time.time(); vids, _ = run_multi(base, lo_workflow(w, batch, lnames, width, height, frames, fps), w["timeout"], prof=pb); T["job_b"] = round(time.time() - t, 1); log(wsprobe.describe("job B (low-noise)", pb))
    for k, s in enumerate(shots):
        d = vids.get(str(4200 + k))
        if not d: raise comfy.ComfyError(f"no clip came back for shot {s['i']}")
        out_for(s["i"]).write_bytes(d)
    st["lat"] = None                                                                                   # the latents are not needed again
