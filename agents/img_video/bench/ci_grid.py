"""3090 / Qwen-Image 2.1: same plain prompts at several settings; one side-by-side row per prompt goes to Telegram as soon as its renders are done."""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.expanduser("~/RoyVa/agents/img_video"))
from img_video import comfy, config

here = os.path.dirname(os.path.abspath(__file__)); out = os.path.expanduser("~/RoyVa/runtime/bench/grid"); os.makedirs(out, exist_ok=True)
PROMPTS = ["Albert Einstein struggling to unlock an iPhone",
           "a funny Albert Einstein doing a TikTok dance in his lab",
           "a weathered lighthouse keeper reading a newspaper on a rocky shore at dusk, photograph",
           "a street food stall in Mumbai at night, photograph",
           "a cat wearing a tiny chef hat cooking pasta",
           "a person standing with their back to the sun, looking at a rainbow",
           "an astronaut riding a horse on Mars",
           "a hand-drawn infographic explaining how the water cycle works"]
SETS = [("8 steps cfg 4", 8, 4.0), ("30 steps cfg 4", 30, 4.0), ("25 steps cfg 1", 25, 1.0)]
cfg, caps = config.load(); base = cfg["comfy"]["url"]
c0 = dict(cfg["comfy"], backend="qwen-image-21", qwen_lora="", timeout=900)
comfy.preflight(base, c0); comfy.wait_until_free(base, log=print)
env = dict(os.environ)
for line in open(os.path.expanduser("~/.config/opencode/telegram/bot.env")):
    if "=" in line and not line.startswith("#"): k, v = line.strip().split("=", 1); env[k] = v.strip('"\'')
sender = os.path.join(os.path.dirname(os.path.abspath(__file__)), "send_photo.mjs")
allt = {s[0]: [] for s in SETS}
for i, p in enumerate(PROMPTS, 1):
    files, caps_txt = [], []
    for name, steps, cs in SETS:
        png, secs = comfy.generate_image(base, dict(c0, qwen_steps=steps, qwen_cfg=cs), p, 1024, 1024, 4242 + i)
        f = f"{out}/{i:02d}_{steps}_{int(cs)}.png"; open(f, "wb").write(png); files.append(f); allt[name].append(secs); caps_txt.append(f"{name} {secs:.1f} s")
        print(f"{i} {name} {secs:.1f}s  {p}", flush=True)
    row = f"{out}/row_{i:02d}.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *sum([["-i", f] for f in files], []), "-filter_complex", "".join(f"[{k}]scale=640:640[s{k}];" for k in range(3)) + "[s0][s1][s2]hstack=3", row], check=True)
    cap = f"🤖 Claude: 3090 Qwen-Image 2.1, plain prompt, same seed. L→R: " + " | ".join(caps_txt) + f"\n'{p}'"
    subprocess.run(["node", sender, cap, row], env=env, capture_output=True, timeout=120)
print(json.dumps({k: {"first": round(v[0], 1), "mean_warm": round(sum(v[1:]) / max(1, len(v) - 1), 1)} for k, v in allt.items()}))
