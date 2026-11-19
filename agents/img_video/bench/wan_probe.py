"""Runs ONE small Wan job pair (high-noise then low-noise, 3 clips) on the 3090 using the stills/motions of the newest job that has a storyboard, and prints the per-node profile and the
raw timeline. Used by scripts/remote/wan-load-watch.sh to see what the box does during the ~21 s first sampler call. Unique seeds every run (ComfyUI would otherwise reuse cached results)."""
import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pathlib import Path
from img_video import config, comfy, wan, wsprobe

cfg, caps = config.load(); base = cfg["comfy"]["url"]; w = cfg["wan"]
jobs = sorted((p for p in (Path(__file__).resolve().parents[1] / "jobs").glob("*") if (p / "video" / "storyboard.json").exists()), key=lambda p: p.stat().st_mtime)
sb = json.loads((jobs[-1] / "video" / "storyboard.json").read_text()); shots = sb["shots"][:3]; width, height = sb["wan"]; frames = caps["video"]["frames"]
comfy.wait_until_free(base); seed0 = int(time.time()) % 100000; tag = f"wl{seed0}"
names = [wan.upload(base, open(s["image"], "rb").read(), f"{tag}_still{s['i']}.png") for s in shots]
batch = [{"prompt": s["motion"], "image_name": n, "seed": seed0 + s["i"]} for s, n in zip(shots, names)]
t0 = time.time(); print(f"WAN_START {t0:.2f}", flush=True)
pa = {}; _, lat = wan.run_multi(base, wan.hi_workflow(w, batch, width, height, frames), w["timeout"], prof=pa); ta = time.time(); print(f"JOB_A_DONE {ta:.2f} ({ta - t0:.1f}s)", flush=True)
lnames = [wan.upload(base, lat[str(2200 + k)], f"{tag}_hi{k}.latent") for k in range(len(shots))]
pb = {}; tb0 = time.time(); wan.run_multi(base, wan.lo_workflow(w, batch, lnames, width, height, frames, 16), w["timeout"], prof=pb); tb = time.time(); print(f"JOB_B_START {tb0:.2f} JOB_B_DONE {tb:.2f} ({tb - tb0:.1f}s)", flush=True)
for label, p in (("A", pa), ("B", pb)): print(wsprobe.describe(label, p), flush=True)
