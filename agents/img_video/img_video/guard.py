"""The 3090 boundary: nothing may reach the shared GPU box with an oversized prompt or while another job holds it. Prompts of about 1,200 characters or more went with abrupt resets of that box on 2026-11-17.
Three tools: `cut` (word-boundary cut), `fit_prompt` (a rewrite by the local writer to fit the cap, then a cut as the last resort; used for requests that bring their own prompt), `trim_workflow`
(a hard ceiling on every text-encoder input of a ComfyUI graph, applied at the single place the agent posts graphs) and `gpu_lock` (one job at a time on the box, across the agent and the chat image tools)."""
import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from . import llm

ROOT = Path(__file__).resolve().parents[3]
LOCK = Path(os.environ.get("ROYVA_GPU_LOCK", ROOT / "runtime" / "gateway" / "gpu3090.lock"))


def cut(v, n):
    """Cut text to at most n characters at a word boundary."""
    if len(v) <= n: return v
    t = v[:n]; t = t[:t.rfind(" ")] if " " in t else t
    return t.rstrip(" ,;:-") or v[:n]


def fit_prompt(cfg, text, cap=None, log=None):
    """A picture description of any length -> one of at most `cap` characters. The local writer rewrites it (up to 3 rounds, more freedom each time); if that does not get it under the cap, or the writer is
    down, it is cut at a word boundary. Never raises. Returns {"prompt", "original_chars", "chars", "method": none | rewrite | trim}."""
    cap = cap or cfg["limits"]["image_prompt_chars"]
    cur = " ".join(str(text).split()); n0 = len(cur)
    if n0 <= cap: return {"prompt": cur, "original_chars": n0, "chars": n0, "method": "none"}
    for rnd, temp in enumerate((0.2, 0.5, 0.8), 1):
        try:
            o = llm.ask_json(cfg["llm"], "You shorten picture descriptions without losing what the picture must show.",
                f"Rewrite this picture description to at most {cap} characters (it is {len(cur)}). Keep the main subject and what it is doing, the setting, the key colors, and any text that must appear in quotes; "
                f"drop adjectives, repeated ideas and extra detail; write complete phrases.\nDescription: {json.dumps(cur, ensure_ascii=False)}\nReturn JSON: {{\"prompt\": the shortened description}}",
                temperature=temp, max_tokens=900, check=lambda o: None if isinstance(o, dict) and isinstance(o.get("prompt"), str) and o["prompt"].strip() else "need a non-empty prompt")
        except llm.LLMError:
            break
        new = " ".join(o["prompt"].split())
        if log: log(f"  prompt rewrite {rnd}: {len(cur)} -> {len(new)} characters (cap {cap})")
        cur = new
        if len(cur) <= cap: return {"prompt": cur, "original_chars": n0, "chars": len(cur), "method": "rewrite"}
    out = cut(cur, cap)
    if log: log(f"  prompt trimmed at a word boundary: {len(cur)} -> {len(out)} characters (cap {cap})")
    return {"prompt": out, "original_chars": n0, "chars": len(out), "method": "trim"}


AUDIT = Path(os.environ.get("ROYVA_PROMPT_AUDIT", ROOT / "runtime" / "gateway" / "prompts_sent.jsonl"))


def audit(rows):
    """One JSON line per text input posted to the 3090: how long it was, how long it was when sent. Lets anyone check afterwards that nothing over the ceiling went out. A failure here never stops a render."""
    if not rows: return
    try:
        AUDIT.parent.mkdir(parents=True, exist_ok=True)
        if AUDIT.exists() and AUDIT.stat().st_size > 5_000_000: AUDIT.replace(AUDIT.with_suffix(".jsonl.1"))
        with open(AUDIT, "a") as f:
            for r in rows: f.write(json.dumps(r) + "\n")
    except OSError: pass


def trim_workflow(wf, hard, log=None):
    """Ceiling on EVERY string input of a ComfyUI graph (done in place), not only the ones of nodes we recognise as text encoders: a prompt could arrive through any node (a string primitive, a different encoder). File names and
    option values are far shorter than the ceiling, so nothing else is touched. Text-encoder inputs and any string over 100 characters are recorded. Returns how many were cut. The last line of defence: nothing longer than `hard` is posted."""
    n, rows = 0, []
    for node in (wf or {}).values():
        if not isinstance(node, dict): continue
        inp = node.get("inputs") or {}; encoder = "TextEncode" in str(node.get("class_type", ""))
        for k, v in list(inp.items()):
            if not isinstance(v, str): continue
            was = len(v)
            if was > hard:
                inp[k] = cut(v, hard); n += 1
                if log: log(f"  3090 guard: a {was}-character input ({node.get('class_type')}.{k}) was cut to {len(inp[k])} (ceiling {hard})")
            if encoder or was > 100: rows.append({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "pid": os.getpid(), "node": str(node.get("class_type")), "field": k, "was": was, "sent": len(inp[k]), "ceiling": hard})
    audit(rows)
    return n


@contextmanager
def gpu_lock(wait_s=900, log=None):
    """One job at a time on the 3090, shared with the chat image tools (same lock file). Waits up to wait_s, then raises TimeoutError."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    f = open(LOCK, "w"); t0 = time.time(); told = False
    try:
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); break
            except BlockingIOError:
                if time.time() - t0 > wait_s: raise TimeoutError(f"the 3090 is busy with another job (waited {int(wait_s)} s)")
                if log and not told: log("  waiting for the 3090: another job holds the GPU lock"); told = True
                time.sleep(2)
        yield
    finally:
        f.close()
