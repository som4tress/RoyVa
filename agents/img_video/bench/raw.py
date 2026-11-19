import subprocess, os, time
M = os.path.expanduser("~/llm-server/models/image/qwen-image-2.1")
D = os.path.expanduser("~/llm-server/sdcpp/master-1086")
OUT = os.path.expanduser("~/RoyVa/runtime/bench/local_sd")
os.makedirs(OUT, exist_ok=True)
P = ["how a rainbow forms: sunlight entering a raindrop and splitting into colors",
     "a person standing with their back to the sun, looking at a rainbow",
     "a rainbow over a green valley after the rain"]
S = [("l4", ["--steps", "4", "--cfg-scale", "1.0"], "<lora:lightning4:1>"),
     ("full", ["--steps", "30", "--cfg-scale", "4.0"], "")]
for tag, a, lo in S:
    for i, p in enumerate(P, 1):
        t = time.time()
        r = subprocess.run(["flock", os.path.expanduser("~/RoyVa/runtime/gateway/image.lock"), f"{D}/sd-cli",
            "--diffusion-model", f"{M}/qwen-image-2.1-Q8_0.gguf", "--vae", f"{M}/qwen_image_2.1_vae_bf16.safetensors",
            "--llm", f"{M}/Qwen3-VL-8B-Instruct-Q8_0.gguf", "--lora-model-dir", f"{M}/loras",
            "-p", (p + " " + lo).strip(), *a, "--sampling-method", "euler", "-W", "1024", "-H", "1024",
            "--flash-attn", "on", "--seed", "7", "-o", f"{OUT}/{tag}_{i}.png"],
            cwd=D, env={**os.environ, "LD_LIBRARY_PATH": D}, capture_output=True, text=True)
        print(tag, i, r.returncode, round(time.time() - t, 1), flush=True)
