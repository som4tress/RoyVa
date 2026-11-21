"""N pictures at EXACTLY L characters each (real prompt text from finished jobs, each picture a different window of it; the length is asserted, never "about"). Logged and fsynced before each send; after each picture
the picture and its full prompt go to the owner's Telegram. Stops at the first failure. Runs only here (the in-process ceiling of img_video.guard is raised for this script; the live agent keeps 500).
usage: python3 prompt_len_fixed.py [length, default 800] [count, default 20]"""
import glob, json, os, subprocess, sys, time

sys.path.insert(0, os.path.expanduser("~/RoyVa/agents/img_video"))
from img_video import comfy, config

L = int(sys.argv[1]) if len(sys.argv) > 1 else 800; N = int(sys.argv[2]) if len(sys.argv) > 2 else 20
cfg, caps = config.load(); c = dict(cfg["comfy"], timeout=300); base = c["url"]; comfy._HARD[:] = [L + 100]
jobs = sorted(glob.glob(os.path.expanduser("~/RoyVa/agents/img_video/jobs/*/items.json")))[-8:]
text = " ".join(x["image_prompt"] for j in jobs for x in json.load(open(j))["items"])
step = (len(text) - L) // (N - 1); assert step > 0, f"not enough text ({len(text)} chars) for {N} windows of {L}"
out = os.path.expanduser(f"~/RoyVa/runtime/bench/prompt_fixed{L}"); os.makedirs(out, exist_ok=True); logf = open(out + "/log.txt", "a")
env = dict(os.environ); [env.setdefault(k, v) for k, v in (l.strip().split("=", 1) for l in open(os.path.expanduser("~/.config/opencode/telegram/bot.env")) if "=" in l and not l.startswith("#"))]


def log(s):
    line = time.strftime("%H:%M:%S ") + s; print(line, flush=True); logf.write(line + "\n"); logf.flush(); os.fsync(logf.fileno())


def tell(caption, png):
    try: subprocess.run(["node", os.path.expanduser("~/RoyVa/agents/img_video/bench/send_photo.mjs"), caption[:1024], png], env=env, timeout=120, capture_output=True)
    except Exception as e: log(f"  telegram send failed: {e}")      # noqa: BLE001


comfy.preflight(base, c); comfy.wait_until_free(base, log=log)
log(f"start: {N} pictures at exactly {L} characters, {len(text)} chars of source text from {len(jobs)} jobs")
for i in range(1, N + 1):
    s = (i - 1) * step; p = text[s:s + L]; assert len(p) == L, len(p)
    log(f"SENDING {i}/{N} len={len(p)}: {p}")
    png, secs = comfy.generate_image(base, c, p, 1024, 1024, 6000 + i)
    f = f"{out}/pic{i:02d}_len{len(p)}.png"; open(f, "wb").write(png); log(f"done    {i}/{N} len={len(p)} in {secs:.1f}s")
    tell(f"{i}/{N} - {len(p)} chars, {secs:.1f}s\n{p}", f)
log("ALL DONE, no trip")
