"""ComfyUI custom node with NO nodes: only a hook. No string input of any graph submitted to this ComfyUI may be longer than MAX_CHARS (default 500): it is cut at a word boundary before the graph is queued, whoever sent it
(RoyVa's agent, a script, ComfyUI's own web page). Every submitted text-encoder input and every string over 100 characters is recorded in <log dir>/prompt_guard.jsonl.
Why: on 2026-11-17 the 3090 box reset abruptly six times during picture generation, four of them with prompts of 1,000-1,500 characters. Client-side guards cannot cover a client nobody wrote yet; this one sits at the server.
ComfyUI swallows errors raised by an on-prompt handler (the graph then goes through untrimmed), so the handler never raises, and prompt-guard-verify.sh proves after every restart that it is really active.
Install: scripts/remote/prompt-guard.sh (copies this file to ~/comfyui/data/custom_nodes/), then restart ComfyUI. Overrides: COMFY_MAX_PROMPT_CHARS, COMFY_PROMPT_GUARD_LOG_DIR."""
import json
import logging
import os
import time

MAX_CHARS = int(os.environ.get("COMFY_MAX_PROMPT_CHARS", "500"))
LOG = os.path.join(os.environ.get("COMFY_PROMPT_GUARD_LOG_DIR", "/data"), "prompt_guard.jsonl")
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}


def cut(v, n):
    if len(v) <= n: return v
    t = v[:n]; t = t[:t.rfind(" ")] if " " in t else t
    return t.rstrip(" ,;:-") or v[:n]


def limit_graph(graph, max_chars=MAX_CHARS):
    """Cut every oversized string input of a graph in place. Returns one record per text-encoder input / long string: {node, field, was, sent}."""
    rows = []
    for node_id, node in (graph or {}).items():
        if not isinstance(node, dict): continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict): continue
        encoder = "TextEncode" in str(node.get("class_type", ""))
        for k, v in list(inputs.items()):
            if not isinstance(v, str): continue
            was = len(v)
            if was > max_chars: inputs[k] = cut(v, max_chars)
            if encoder or was > 100: rows.append({"node": f"{node_id}:{node.get('class_type')}", "field": k, "was": was, "sent": len(inputs[k])})
    return rows


def on_prompt(json_data):
    try:
        rows = limit_graph((json_data or {}).get("prompt"))
        if rows:
            try:
                with open(LOG, "a") as f:
                    for r in rows: f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "max": MAX_CHARS, **r}) + "\n")
            except OSError: pass                                         # a log failure must not stop the guard
            cut_n = [r for r in rows if r["was"] > MAX_CHARS]
            if cut_n: logging.warning("[prompt_length_guard] cut %d oversized input(s): %s", len(cut_n), ", ".join(f"{r['node']}.{r['field']} {r['was']}->{r['sent']}" for r in cut_n))
    except Exception as e:                                               # noqa: BLE001  (never raise: ComfyUI would let the graph through untrimmed)
        logging.error("[prompt_length_guard] failed: %s", e)
    return json_data


try:
    from server import PromptServer
    PromptServer.instance.add_on_prompt_handler(on_prompt)
    logging.info("[prompt_length_guard] active: no string input over %d characters reaches a graph", MAX_CHARS)
except Exception as e:                                                   # noqa: BLE001  (outside ComfyUI, e.g. in the tests, there is no server)
    logging.warning("[prompt_length_guard] NOT registered (%s); prompt-guard-verify.sh will say so", e)
