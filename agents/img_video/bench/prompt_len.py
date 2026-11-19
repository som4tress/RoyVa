"""Does prompt length make the 3090 box reset? Sends the same director prompt on the 3090 cut to increasing lengths, 2 pictures per length, same settings as the real job.
Each step is logged and fsynced BEFORE it is sent, so after a crash the log shows the last length that was in flight.
usage: python3 prompt_len.py [lengths comma list, default 60,300,700,1200,1950] [pictures per length, default 2]"""
import glob, json, os, sys, time

sys.path.insert(0, os.path.expanduser("~/RoyVa/agents/img_video"))
from img_video import comfy, config

lengths = [int(x) for x in (sys.argv[1] if len(sys.argv) > 1 else "60,300,700,1200,1950").split(",")]
per = int(sys.argv[2]) if len(sys.argv) > 2 else 2
cfg, caps = config.load(); c = dict(cfg["comfy"], timeout=300); base = c["url"]
job = sorted(glob.glob(os.path.expanduser("~/RoyVa/agents/img_video/jobs/*gpus-wo*")))[-1]
d = json.load(open(job + "/direction.json")); items = json.load(open(job + "/items.json"))["items"]
full = max((x["image_prompt"] for x in items), key=len); full = f"{full.rstrip('. ')}, {d['style_line']}, {cfg['policy'].get('image_text', '')}"
out = os.path.expanduser("~/RoyVa/runtime/bench/prompt_len"); os.makedirs(out, exist_ok=True); logf = open(out + "/log.txt", "a")


def log(s):
    line = time.strftime("%H:%M:%S ") + s; print(line, flush=True); logf.write(line + "\n"); logf.flush(); os.fsync(logf.fileno())


def cut(text, n):
    if n >= len(text): return text
    t = text[:n]; return t[:t.rfind(" ")] if " " in t else t


comfy.preflight(base, c); comfy.wait_until_free(base, log=log)
log(f"start: source job {os.path.basename(job)}, full prompt {len(full)} chars, lengths {lengths}, {per} per length; GPU cap check separately")
for n in lengths:
    p = cut(full, n)
    for k in range(per):
        log(f"SENDING len={len(p)} pic {k + 1}/{per}")
        png, secs = comfy.generate_image(base, c, p, 1024, 1024, 4000 + n + k)
        open(f"{out}/len{n:04d}_{k + 1}.png", "wb").write(png); log(f"done    len={len(p)} pic {k + 1}/{per} in {secs:.1f}s")
log("ALL DONE, no reset")
