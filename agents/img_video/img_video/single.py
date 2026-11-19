"""One picture from the user's own words (no director, nothing planned or added). A prompt over the cap is shortened by the guard (local writer, then a word-boundary cut). It renders on the 3090 under the
shared GPU lock; if the box is unreachable or busy it falls back to this machine's GPU (the local renderer), as the old chat image tool did. Never raises: returns a dict with ok true or false."""
import secrets
import time
from pathlib import Path

from . import comfy, config, guard, local_sd
from .jobs import Job


def make_image(cfg, caps, prompt, aspect="1:1", size=None, seed=None, log=None):
    root = config.jobs_dir(cfg); root.mkdir(parents=True, exist_ok=True)
    job = Job.create(root, {"query": str(prompt)[:1000], "aspect": aspect, "mode": "image"}); job.state["status"] = "running"; job.save()
    say = log or job.log
    try:
        w, h = size or tuple(caps["aspect"][aspect]); seed = int(seed) if seed is not None else secrets.randbelow(2**31)
        fit = guard.fit_prompt(cfg, prompt, log=say)
        text = fit["prompt"]; backend, note = "local", ""
        if cfg["image"]["backend"] == "comfy":
            try:
                comfy.preflight(cfg["comfy"]["url"], cfg["comfy"])
                with guard.gpu_lock(wait_s=15, log=say):
                    png, secs = comfy.generate_image(cfg["comfy"]["url"], cfg["comfy"], text, w, h, seed); backend = "3090"
            except (comfy.ComfyError, TimeoutError, OSError) as e:                       # unreachable, busy, refused: this machine's GPU instead
                note = f"the 3090 was not used ({str(e)[:120]}), so this machine's GPU drew it"
                say("  " + note)
        if backend != "3090":
            local_sd.preflight(cfg["local"]); png, secs = local_sd.generate_image(cfg["local"], text, w, h, seed, say)
        (job.dir / "images").mkdir(exist_ok=True); path = job.dir / "images" / "01.png"; path.write_bytes(png)
        job.state["status"] = "done"; job.save()
        return {"ok": True, "job": job.id, "image_path": str(path), "prompt_used": text, "original_chars": fit["original_chars"], "chars": fit["chars"], "method": fit["method"],
                "backend": backend, "secs": round(secs, 1), "seed": seed, "width": w, "height": h, "note": note}
    except Exception as e:                                                               # noqa: BLE001  (a failure is still a machine-readable answer)
        job.state["status"] = "failed"; job.save()
        return {"ok": False, "job": job.id, "error": f"{type(e).__name__}: {str(e)[:300]}"}
