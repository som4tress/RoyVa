"""Steps the picture prompt from 500 to 650 characters, ONE picture per length (10 lengths), real prompt text from a finished job, same settings as a real job.
Each step is logged and fsynced BEFORE it is sent, so after a trip the log shows the length that was in flight; it stops at the first failure.
Runs only here (the in-process ceiling of img_video.guard is raised for this script; the live agent keeps 500).
usage: python3 prompt_len_step.py [job folder name, default newest job with items.json]"""
import glob, json, os, sys, time

sys.path.insert(0, os.path.expanduser("~/RoyVa/agents/img_video"))
from img_video import comfy, config

cfg, caps = config.load(); c = dict(cfg["comfy"], timeout=300); base = c["url"]
comfy._HARD[:] = [700]
jobs = os.path.expanduser("~/RoyVa/agents/img_video/jobs"); job = os.path.join(jobs, sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(sorted(glob.glob(jobs + "/*/items.json"))[-1])
text = " ".join(x["image_prompt"] for x in json.load(open(job + "/items.json"))["items"])
lengths = [round(500 + i * 150 / 9) for i in range(10)]
out = os.path.expanduser("~/RoyVa/runtime/bench/prompt_step"); os.makedirs(out, exist_ok=True); logf = open(out + "/log.txt", "a")


def log(s):
    line = time.strftime("%H:%M:%S ") + s; print(line, flush=True); logf.write(line + "\n"); logf.flush(); os.fsync(logf.fileno())


def cut(t, n):
    t = t[:n]; return t[:t.rfind(" ")] if " " in t else t


comfy.preflight(base, c); comfy.wait_until_free(base, log=log)
log(f"start: job {os.path.basename(job)}, text {len(text)} chars, lengths {lengths}")
for i, n in enumerate(lengths, 1):
    p = cut(text, n)
    log(f"SENDING {i}/10 len={len(p)}")
    png, secs = comfy.generate_image(base, c, p, 1024, 1024, 5000 + i)
    open(f"{out}/step{i:02d}_len{len(p)}.png", "wb").write(png); log(f"done    {i}/10 len={len(p)} in {secs:.1f}s")
log("ALL DONE, no trip")
