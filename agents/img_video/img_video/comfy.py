"""The agent's own small ComfyUI client (HTTP only, standard library). Text-to-image with FLUX.2 klein, no reference images.
Rules from the handoff: never call /free (host-RAM OOM at the container cap), one job at a time on the shared box, check model names before any GPU work."""
import json
import random
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import config, guard

MAX_PNG = 40_000_000
_HARD = []


class ComfyError(RuntimeError):
    pass


TRANSIENT_WAITS = (2, 4, 8, 15)


def retrying(fn, waits=None):
    """Runs fn(); if the box cannot be reached AT ALL (the name does not resolve: the .local mDNS name drops out for a second now and then, or the connection is refused) it waits and tries again, up to 4 times.
    Only failures that happen before any request is sent are retried, so posting a job twice is not possible; every other error is raised at once. A 17-minute video must not die of a one-second name lookup glitch (seen 2026-11-19)."""
    for w in tuple(TRANSIENT_WAITS if waits is None else waits) + (None,):
        try: return fn()
        except urllib.error.URLError as e:
            if w is None or not isinstance(getattr(e, "reason", None), (socket.gaierror, ConnectionRefusedError)): raise
            print(f"  ComfyUI not reachable ({e.reason}); trying again in {w} s", flush=True); time.sleep(w)


def _hard():
    if not _HARD: lim = config.load()[0]["limits"]; _HARD.append(min(lim["hard_prompt_chars"], lim["image_prompt_chars"]))       # never above the cap
    return _HARD[0]


def _call(base, path, body=None, timeout=30, limit=MAX_PNG):
    if path == "/prompt" and body: guard.trim_workflow(body.get("prompt"), _hard(), log=lambda m: print(m, flush=True))      # nothing oversized reaches the 3090, whoever the caller is
    req = urllib.request.Request(base.rstrip("/") + path, data=None if body is None else json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    def go():
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(limit + 1)
    return retrying(go)


def upload(base, data: bytes, name: str):
    """Put a file into the server's input folder (a picture, a saved latent, a reference photo). Returns the name the server stored it under."""
    bd = uuid.uuid4().hex
    body = (f'--{bd}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + data + \
           (f'\r\n--{bd}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n--{bd}--\r\n').encode()
    req = urllib.request.Request(base.rstrip("/") + "/upload/image", data=body, headers={"Content-Type": f"multipart/form-data; boundary={bd}"})
    try:
        def go():
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read()).get("name", name)
        return retrying(go)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ComfyError(f"upload of {name} failed: {e}")


def _combo(base, node, field):
    """The file names ComfyUI offers for a loader node, e.g. ('UNETLoader', 'unet_name')."""
    d = json.loads(_call(base, f"/object_info/{node}"))[node]["input"]["required"][field]
    return list(d[0]) if isinstance(d[0], list) else []


FILES = {"flux2-klein": (("UNETLoader", "unet_name", "unet"), ("CLIPLoader", "clip_name", "clip"), ("VAELoader", "vae_name", "vae")),
         "z-image-turbo": (("UNETLoader", "unet_name", "zimage_unet"), ("CLIPLoader", "clip_name", "zimage_clip"), ("VAELoader", "vae_name", "zimage_vae")),
         "qwen-image-21": (("UNETLoader", "unet_name", "qwen_unet"), ("CLIPLoader", "clip_name", "qwen_clip"), ("VAELoader", "vae_name", "qwen_vae"))}


def backend(c):
    b = c.get("backend", "flux2-klein")
    if b not in FILES: raise ComfyError(f"unknown image backend '{b}' (choose one of {', '.join(FILES)})")
    return b


def preflight(base, cfg_comfy):
    """Fail loudly if ComfyUI is unreachable or a configured model file is not offered (a silently wrong default once cost us a day of misleading benchmarks)."""
    try:
        json.loads(_call(base, "/system_stats", timeout=10))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ComfyError(f"ComfyUI at {base} is not reachable: {e}")
    missing = []
    need = list(FILES[backend(cfg_comfy)])
    if backend(cfg_comfy) == "qwen-image-21" and cfg_comfy.get("qwen_lora"): need.append(("LoraLoaderModelOnly", "lora_name", "qwen_lora"))
    for node, field, key in need:
        have = _combo(base, node, field)
        if cfg_comfy[key] not in have:
            missing.append(f"{node}.{field}: '{cfg_comfy[key]}' not in {len(have)} offered files")
    if missing:
        raise ComfyError("model files not available on the ComfyUI server: " + "; ".join(missing))


def queue_state(base):
    """(running, pending) job counts on the server."""
    q = json.loads(_call(base, "/queue", timeout=15))
    return len(q.get("queue_running", [])), len(q.get("queue_pending", []))


def wait_until_free(base, timeout=900, poll=5, log=lambda m: None):
    """The box is shared: do not pile onto somebody else's job. Waits until nothing is running or queued (or raises on timeout)."""
    t0 = time.time()
    while True:
        r, p = queue_state(base)
        if r == 0 and p == 0: return
        if time.time() - t0 > timeout: raise ComfyError(f"ComfyUI stayed busy for {timeout}s ({r} running, {p} pending)")
        log(f"ComfyUI busy ({r} running, {p} pending), waiting")
        time.sleep(poll)


def t2i_workflow(prompt, width, height, seed, c):
    """FLUX.2 klein text-to-image graph: the same nodes the reference-edit graph uses, minus the reference images (so no KV cache either)."""
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": c["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": c["clip"], "type": "flux2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": c["vae"]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "6": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "7": {"class_type": "Flux2Scheduler", "inputs": {"steps": c["steps"], "width": width, "height": height}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "9": {"class_type": "CFGGuider", "inputs": {"model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0], "cfg": 1.0}},
        "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "11": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["10", 0], "guider": ["9", 0], "sampler": ["8", 0], "sigmas": ["7", 0], "latent_image": ["6", 0]}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "13": {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": "img_video"}},
    }


def zimage_workflow(prompt, width, height, seed, c):
    """Z-Image Turbo text-to-image graph (the model RoyVa's own image tool uses on this ComfyUI): 8 steps, cfg 1, empty negative."""
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": c["zimage_unet"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": c["zimage_clip"], "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": c["zimage_vae"]}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0], "seed": seed, "steps": c["zimage_steps"], "cfg": 1.0,
                                                    "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "img_video"}},
    }


def qwen21_workflow(prompt, width, height, seed, c, refs=None):
    """Qwen-Image 2.1 text-to-image graph (the structure of ComfyUI's own 'Text to Image (Qwen Image 2.1)' template): 7B INT8 ConvRot diffusion model, Qwen3-VL-8B text encoder.
    The base template samples 25 steps, cfg 1, euler/simple; qwen_lora (e.g. the Lightning 4-step LoRA, cfg 1) is optional. The text node's negative prompt only matters when cfg > 1.
    `refs` = names of reference photos already uploaded to the server's input folder (a person to keep in the picture): the text node takes up to 16 reference images ("seen by the text encoder and spliced into the sequence as VAE latents")
    and needs the VAE to encode them; `qwen_ref_resolution` sets the size they are resized to (about N x N pixels)."""
    model = ["1", 0]; g = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": c["qwen_unet"], "weight_dtype": "default"}}}
    if c.get("qwen_lora"):
        g["9"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": c["qwen_lora"], "strength_model": c.get("qwen_lora_weight", 1.0)}}; model = ["9", 0]
    g.update({
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": c["qwen_clip"], "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": c["qwen_vae"]}},
        "4": {"class_type": "TextEncodeQwenImage21", "inputs": {"clip": ["2", 0], "prompt": prompt, "negative_prompt": c.get("qwen_negative", ""), "resolution": int(c.get("qwen_ref_resolution", 1024)) if refs else 1024}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {"model": model, "positive": ["4", 0], "negative": ["4", 1], "latent_image": ["5", 0], "seed": seed, "steps": c["qwen_steps"], "cfg": c["qwen_cfg"],
                                                    "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "img_video"}}})
    for k, name in enumerate((refs or [])[:16], 1):
        g[f"3{k:02d}"] = {"class_type": "LoadImage", "inputs": {"image": name}}
        g["4"]["inputs"][f"images.image_{k}"] = [f"3{k:02d}", 0]
    if refs: g["4"]["inputs"]["vae"] = ["3", 0]
    return g


WORKFLOWS = {"flux2-klein": t2i_workflow, "z-image-turbo": zimage_workflow, "qwen-image-21": qwen21_workflow}


def run(base, wf, timeout=600, poll=1.0):
    """Submit one graph and return the first output image as PNG bytes."""
    t0 = time.time()
    try:
        pid = json.loads(_call(base, "/prompt", {"prompt": wf}))["prompt_id"]
    except urllib.error.HTTPError as e:
        raise ComfyError(f"ComfyUI refused the graph (HTTP {e.code}): {e.read(600).decode('utf-8', 'replace')}")
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        raise ComfyError(f"could not submit to ComfyUI: {e}")
    while time.time() - t0 < timeout:
        time.sleep(poll)
        hist = json.loads(_call(base, f"/history/{pid}")).get(pid)
        if not hist: continue
        st = hist.get("status", {})
        if st.get("status_str") == "error":
            msgs = [m for m in st.get("messages", []) if m and m[0] == "execution_error"]
            raise ComfyError("ComfyUI failed the job: " + str((msgs[0][1].get("exception_message") if msgs else "") or "unknown error")[:300])
        for node in hist.get("outputs", {}).values():
            for img in node.get("images", []):
                q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")})
                return _call(base, f"/view?{q}", timeout=60)
    raise ComfyError(f"ComfyUI did not finish within {timeout}s")


WARM_PROMPT = "a plain grey square"


def warm(base, c, log=lambda m: None):
    """Best effort: make ComfyUI read the picture model from disk NOW (it only loads on the first graph that needs it, ~27 s on the first picture), by running one throwaway 1-step 256x256 picture.
    Only for the qwen-image-21 backend, and only when the box is idle (it is shared). Returns the seconds it took, or None when skipped. ComfyUI has no load-only call."""
    if backend(c) != "qwen-image-21": return None
    r, p = queue_state(base)
    if r or p: log("  picture model warm-up skipped: ComfyUI is busy"); return None
    t = time.time()
    run(base, qwen21_workflow(WARM_PROMPT, 256, 256, random.randrange(2**31), dict(c, qwen_steps=1)), timeout=c.get("timeout", 600))     # a fresh seed every time: an identical graph would be served from ComfyUI's result cache
    return time.time() - t


def interrupt(base):
    """Ask ComfyUI to stop the graph it is running now (used when a job is cancelled). Best effort; never raises."""
    try: _call(base, "/interrupt", {}, timeout=10)
    except Exception: return False                                     # noqa: BLE001
    return True


def generate_image(base, c, prompt, width, height, seed, refs=None):
    """One text-to-image call; returns (png_bytes, seconds). `refs` (names of uploaded reference photos) is only supported by the qwen-image-21 backend."""
    t = time.time()
    if refs and backend(c) != "qwen-image-21": raise ComfyError("reference photos need the qwen-image-21 backend")
    png = run(base, WORKFLOWS[backend(c)](prompt, width, height, seed, c, **({"refs": refs} if refs else {})), timeout=c.get("timeout", 600))
    return png, time.time() - t
