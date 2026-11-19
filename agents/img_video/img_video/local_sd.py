"""Local text-to-image: stable-diffusion.cpp (`sd-cli`, Vulkan) with Qwen-Image 2.1 Q8 and an optional step-distilled LoRA, all on this machine's GPU.
Takes the same lock as RoyVa's own image tool (runtime/gateway/image.lock), so the two never render at once; it waits for the lock instead of failing."""
import fcntl
import os
import subprocess
import time
from pathlib import Path


class LocalError(RuntimeError):
    pass


def _p(s): return Path(os.path.expanduser(s))


def _files(c):
    m = _p(c["models"])
    f = [_p(c["bin"]) / "sd-cli", m / c["diffusion"], m / c["llm"], m / c["vae"]]
    if c.get("lora"): f.append(m / "loras" / (c["lora"] + ".safetensors"))
    return f


def preflight(c):
    missing = [str(f) for f in _files(c) if not f.exists()]
    if missing: raise LocalError("local image files missing: " + ", ".join(missing))


def generate_image(c, prompt, width, height, seed, log=lambda m: None):
    """One picture; returns (png_bytes, seconds). Steps, cfg and the LoRA come from the [local] config section."""
    preflight(c)
    m, b = _p(c["models"]), _p(c["bin"]); out = Path(c["tmp_dir"]).expanduser() / f"local-{os.getpid()}-{seed}.png"; out.parent.mkdir(parents=True, exist_ok=True)
    p = prompt + (f" <lora:{c['lora']}:{c.get('lora_weight', 1.0)}>" if c.get("lora") else "")
    cmd = [str(b / "sd-cli"), "--diffusion-model", str(m / c["diffusion"]), "--vae", str(m / c["vae"]), "--llm", str(m / c["llm"]), "--lora-model-dir", str(m / "loras"),
           "-p", p, "--steps", str(c["steps"]), "--cfg-scale", str(c["cfg"]), "--sampling-method", "euler", "-W", str(width), "-H", str(height), "--flash-attn", "on", "--seed", str(seed), "-o", str(out)]
    lock_path = _p(c["lock"]); lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lk:
        t0 = time.time()
        while True:
            try: fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB); break
            except OSError:
                if time.time() - t0 > c["timeout"]: raise LocalError("the local image renderer stayed busy")
                log("another picture is rendering on this machine, waiting"); time.sleep(5)
        t = time.time()
        try:
            r = subprocess.run(cmd, cwd=b, env={**os.environ, "LD_LIBRARY_PATH": str(b)}, capture_output=True, text=True, timeout=c["timeout"])
        except subprocess.TimeoutExpired:
            out.unlink(missing_ok=True); raise LocalError(f"local image render timed out after {c['timeout']}s")
        secs = time.time() - t
    if r.returncode != 0 or not out.exists() or out.stat().st_size < 1000:
        raise LocalError("local image render failed: " + (r.stderr or r.stdout or "no output")[-300:].strip())
    png = out.read_bytes(); out.unlink(missing_ok=True)
    return png, secs
