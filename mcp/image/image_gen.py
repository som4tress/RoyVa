"""MCP server (stdio, newline JSON-RPC): text-to-image with Qwen-Image-2.1 (Q8) through stable-diffusion.cpp on the Vulkan GPU.
Tool: generate_image(prompt, width, height, steps, seed). The picture is written under runtime/data/images/ and the result carries
`image_path`; the bridge sends that file back to the chat. One render at a time (a lock file), a hard timeout, bounded sizes, old pictures pruned.
Honors the dry-run flag. Paths can be overridden with ROYVA_SD_BIN / ROYVA_IMAGE_MODELS / ROYVA_IMAGE_DIR."""
import fcntl
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOME = Path.home()
SD_DIR = Path(os.environ.get("ROYVA_SD_BIN", HOME / "llm-server" / "sdcpp" / "master-1086"))
MODELS = Path(os.environ.get("ROYVA_IMAGE_MODELS", HOME / "llm-server" / "models" / "image" / "qwen-image-2.1"))
OUT_DIR = Path(os.environ.get("ROYVA_IMAGE_DIR", ROOT / "runtime" / "data" / "images"))
LOCK = Path(os.environ.get("ROYVA_IMAGE_LOCK", ROOT / "runtime" / "gateway" / "image.lock"))
DRY_FLAG = Path(os.environ.get("ROYVA_DRY_RUN_FLAG", ROOT / "runtime" / "gateway" / "dry_run"))
DRY = lambda: os.environ.get("ROYVA_DRY_RUN") == "1" or DRY_FLAG.exists()
FILES = {"diffusion": "qwen-image-2.1-Q8_0.gguf", "llm": "Qwen3-VL-8B-Instruct-Q8_0.gguf", "vae": "qwen_image_2.1_vae_bf16.safetensors"}
VISION = "mmproj-Qwen3-VL-8B-F16.gguf"        # only needed for editing a photo
INBOX = Path(os.environ.get("ROYVA_INBOX_DIR", ROOT / "runtime" / "data" / "inbox"))   # photos the bridge saved from chat; the only place edit_image reads from
MAX_PROMPT, MIN_SIDE, MAX_SIDE, MIN_STEPS, MAX_STEPS, KEEP = 1500, 512, 1280, 8, 40, 60
CACHE = os.environ.get("ROYVA_IMAGE_CACHE", "easycache")      # "" turns it off
TIMEOUT = int(os.environ.get("ROYVA_IMAGE_TIMEOUT", "900"))
HINT = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}

TOOLS = [{
    "name": "generate_image",
    "description": ("Generate one picture from a text description and send it to the chat. Takes one to a few minutes and the GPU is shared with chat, so call it once per request. "
                    "Write the prompt in English as a concrete visual description (subject, style, setting, lighting, any text that must appear in quotes). Width and height are multiples of 16 "
                    f"between {MIN_SIDE} and {MAX_SIDE} (default 1024x1024)."),
    "inputSchema": {"type": "object", "properties": {
        "prompt": {"type": "string", "description": "What the picture should show."},
        "width": {"type": "integer", "default": 1024}, "height": {"type": "integer", "default": 1024},
        "steps": {"type": "integer", "default": 20, "description": f"{MIN_STEPS}-{MAX_STEPS}; 20 is the recommended quality."},
        "seed": {"type": "integer", "description": "Optional, for a repeatable result."}}, "required": ["prompt"], "additionalProperties": False},
    "annotations": HINT},
    {"name": "edit_image",
     "description": ("Restyle or edit a photo the user sent (for example turn it into a Ghibli-style painting, a museum canvas portrait, or put a stadium behind the person). "
                     "image is the photo's path exactly as given in the request's 'Attached photo' line. Describe the wanted result in English as an instruction ('Turn this photo into a Studio Ghibli style painting, keep the faces recognizable'). "
                     "Takes a few minutes; call it once per request."),
     "inputSchema": {"type": "object", "properties": {
         "image": {"type": "string", "description": "Path of the attached photo."},
         "prompt": {"type": "string", "description": "The edit to make."},
         "steps": {"type": "integer", "default": 20}, "seed": {"type": "integer"}}, "required": ["image", "prompt"], "additionalProperties": False},
     "annotations": HINT}]


def _side(value, name):
    v = int(value)
    if not MIN_SIDE <= v <= MAX_SIDE or v % 16:
        raise ValueError(f"{name} must be a multiple of 16 between {MIN_SIDE} and {MAX_SIDE}")
    return v


def _prune():
    pics = sorted(OUT_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime)
    for p in pics[:-KEEP]:
        p.unlink(missing_ok=True)


def generate_image(args):
    prompt = str(args.get("prompt", "")).strip()
    if not prompt:
        return {"ok": False, "error": "prompt is empty"}
    if len(prompt) > MAX_PROMPT:
        return {"ok": False, "error": f"prompt is too long ({len(prompt)} > {MAX_PROMPT} characters)"}
    width, height = _side(args.get("width", 1024), "width"), _side(args.get("height", 1024), "height")
    steps = max(MIN_STEPS, min(MAX_STEPS, int(args.get("steps", 20))))
    seed = int(args["seed"]) if args.get("seed") is not None else secrets.randbelow(2**31)
    if DRY():
        return {"ok": True, "did": f"[DRY RUN, nothing happened] Would generate a {width}x{height} picture: {prompt[:80]}"}
    missing = [n for n in [SD_DIR / "sd-cli", *(MODELS / f for f in FILES.values())] if not Path(n).exists()]
    if missing:
        return {"ok": False, "error": "image model files are missing: " + ", ".join(Path(m).name for m in missing)}
    return _render(prompt, steps, seed, width, height, None, f"Generated a {width}x{height} picture")


def _size(path):
    """(width, height) of a PNG or JPEG without extra libraries, or None."""
    with open(path, "rb") as f:
        head = f.read(26)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
        if head[:2] == b"\xff\xd8":
            f.seek(2)
            while True:
                b = f.read(1)
                if not b:
                    return None
                if b != b"\xff":
                    continue
                m = f.read(1)
                while m == b"\xff":
                    m = f.read(1)
                if m and m[0] in range(0xC0, 0xD0) and m[0] not in (0xC4, 0xC8, 0xCC):
                    seg = f.read(7)
                    return int.from_bytes(seg[5:7], "big"), int.from_bytes(seg[3:5], "big")
                length = int.from_bytes(f.read(2), "big")
                f.seek(length - 2, 1)
    return None


def edit_image(args):
    prompt = str(args.get("prompt", "")).strip()
    if not prompt:
        return {"ok": False, "error": "prompt is empty"}
    if len(prompt) > MAX_PROMPT:
        return {"ok": False, "error": f"prompt is too long ({len(prompt)} > {MAX_PROMPT} characters)"}
    src = Path(str(args.get("image", ""))).expanduser().resolve()
    if INBOX.resolve() not in src.parents or src.suffix.lower() not in (".jpg", ".jpeg", ".png") or not src.is_file():
        return {"ok": False, "error": "image must be a photo attached to the request (use the path from the 'Attached photo' line)"}
    steps = max(MIN_STEPS, min(MAX_STEPS, int(args.get("steps", 20))))
    seed = int(args["seed"]) if args.get("seed") is not None else secrets.randbelow(2**31)
    dims = _size(src) or (1024, 1024)
    scale = min(1.0, 1024 / max(dims))                      # keep the longest side at most 1024 and sides divisible by 32
    width, height = max(256, round(dims[0] * scale / 32) * 32), max(256, round(dims[1] * scale / 32) * 32)
    if DRY():
        return {"ok": True, "did": f"[DRY RUN, nothing happened] Would edit the photo ({width}x{height}): {prompt[:80]}"}
    if not (MODELS / VISION).exists():
        return {"ok": False, "error": f"editing needs the vision file {VISION}, which is missing"}
    return _render(prompt, steps, seed, width, height, src, f"Edited the photo ({width}x{height})")


def _render(prompt, steps, seed, width, height, ref, label):
    missing = [n for n in [SD_DIR / "sd-cli", *(MODELS / f for f in FILES.values())] if not Path(n).exists()]
    if missing:
        return {"ok": False, "error": "image model files are missing: " + ", ".join(Path(m).name for m in missing)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}.png"
    with open(LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return {"ok": False, "error": "another picture is still being generated; try again in a minute"}
        cmd = [str(SD_DIR / "sd-cli"), "--diffusion-model", str(MODELS / FILES["diffusion"]), "--vae", str(MODELS / FILES["vae"]), "--llm", str(MODELS / FILES["llm"]),
               "-p", prompt, "--steps", str(steps), "--cfg-scale", "6.0", "--sampling-method", "euler", "-W", str(width), "-H", str(height),
               "--diffusion-fa", "--seed", str(seed), "-v", "-o", str(out)]
        if CACHE:                                           # skips steps that barely change the picture: about 2x faster, same look (measured)
            cmd += ["--cache-mode", CACHE]
        if ref is not None:
            cmd += ["-r", str(ref), "--llm_vision", str(MODELS / VISION)]
        started = time.time()
        try:
            run = subprocess.run(cmd, cwd=SD_DIR, env={**os.environ, "LD_LIBRARY_PATH": str(SD_DIR)}, capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            out.unlink(missing_ok=True)
            return {"ok": False, "error": f"image generation timed out after {TIMEOUT}s"}
    if run.returncode != 0 or not out.exists() or out.stat().st_size < 1000:
        return {"ok": False, "error": "image generation failed: " + (run.stderr or run.stdout or "no output")[-300:].strip()}
    _prune()
    secs = round(time.time() - started)
    tokens = sum(int(n) for n in re.findall(r'split prompt .* to (\d+) tokens', (run.stderr or "") + (run.stdout or "")))   # what the Qwen3-VL text encoder read
    return {"ok": True, "did": f"{label} in {secs}s (seed {seed}); it is sent to the chat.", "image_path": str(out), "seed": seed, "secs": secs, "encoder_tokens": tokens}


FUNCS = {"generate_image": generate_image, "edit_image": edit_image}


def handle(msg):
    method, ident = msg.get("method"), msg.get("id")
    if method == "initialize":
        result = {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}}, "serverInfo": {"name": "image-gen", "version": "1.0.0"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        p = msg.get("params", {})
        try:
            result = {"content": [{"type": "text", "text": json.dumps(FUNCS[p.get("name")](p.get("arguments", {})))}]}
        except Exception as e:                                          # noqa: BLE001
            result = {"content": [{"type": "text", "text": json.dumps({"ok": False, "error": str(e)[:300]})}], "isError": True}
    elif ident is None:
        return
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "Method not found"}}), flush=True)
        return
    print(json.dumps({"jsonrpc": "2.0", "id": ident, "result": result}), flush=True)


if __name__ == "__main__":
    for line in sys.stdin:
        if line.strip():
            try:
                handle(json.loads(line))
            except Exception as e:                                      # noqa: BLE001
                print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)[:200]}}), flush=True)
