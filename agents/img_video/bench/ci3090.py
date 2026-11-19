"""Time Qwen-Image 2.1 on the 3090 (ComfyUI) with plain prompts, and send each picture to Telegram as soon as it is generated.
usage: python3 ci3090.py <tag> <steps> <cfg> [lora_file] [count]"""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.expanduser("~/RoyVa/agents/img_video"))
from img_video import comfy, config

tag, steps, cfg_scale = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
lora = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != "-" else ""
count = int(sys.argv[5]) if len(sys.argv) > 5 else 10
here = os.path.dirname(os.path.abspath(__file__)); out = os.path.expanduser(f"~/RoyVa/runtime/bench/c3090_{tag}"); os.makedirs(out, exist_ok=True)
cfg, caps = config.load(); c = dict(cfg["comfy"], backend="qwen-image-21", qwen_steps=steps, qwen_cfg=cfg_scale, qwen_lora=lora, timeout=900)
base = c["url"]
items = json.load(open(os.path.expanduser("~/RoyVa/agents/img_video/jobs/20261116-183338-10-images-explaining-how-a-rainb/items.json")))["items"][:count]
prompts = [f"{x['topic']} (how a rainbow forms)" for x in items]
comfy.preflight(base, c); comfy.wait_until_free(base, log=print)
env = dict(os.environ)
for line in open(os.path.expanduser("~/.config/opencode/telegram/bot.env")):
    if "=" in line and not line.startswith("#"): k, v = line.strip().split("=", 1); env[k] = v.strip('"\'')
sender = os.path.join(os.path.dirname(os.path.abspath(__file__)), "send_photo.mjs")
times = []
for i, p in enumerate(prompts, 1):
    png, secs = comfy.generate_image(base, c, p, 1024, 1024, 1000 + i)
    f = f"{out}/{i:02d}.png"; open(f, "wb").write(png); times.append(secs)
    print(f"{tag} {i}/{len(prompts)} {secs:.1f}s  {p}", flush=True)
    cap = f"🤖 Claude: 3090, Qwen-Image 2.1 INT8, {steps} steps cfg {cfg_scale}{' + LoRA' if lora else ''}: {i}/{len(prompts)} in {secs:.1f} s" + (" (includes model load)" if i == 1 else "") + f"\n'{p}'"
    subprocess.run(["node", sender, cap, f], env=env, capture_output=True, timeout=120)
warm = times[1:] or times
print(json.dumps({"tag": tag, "first": round(times[0], 1), "warm_mean": round(sum(warm) / len(warm), 1), "all": [round(t, 1) for t in times]}))
