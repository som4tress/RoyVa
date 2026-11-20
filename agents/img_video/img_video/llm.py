"""Client for the local writer model (OpenAI-compatible llama-server). JSON in, JSON out. The API key is read from its key file and never logged."""
import json
import os
import base64
import re
import urllib.request


class LLMError(RuntimeError):
    pass


def _chat(c, messages, temperature, max_tokens):
    key = open(os.path.expanduser(c["keyfile"])).read().strip()
    body = {"model": c["model"], "messages": messages, "temperature": temperature, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}, "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(c["url"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]
    except Exception as e:                                           # noqa: BLE001
        raise LLMError(f"local model call failed: {e}")


def _parse(text):
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, flags=re.S)
        if not m: raise
        return json.loads(m.group(0))


def ask_json(c, system, user, temperature=0.6, max_tokens=4000, check=None, attempts=3):
    """One request that must come back as a JSON object. `check(obj)` returns an error string (or ''/None if fine); on failure the model gets `attempts - 1` more chances to fix it (two by default)."""
    msgs = [{"role": "system", "content": system + " Reply with ONLY one JSON object."}, {"role": "user", "content": user}]
    for attempt in range(attempts):
        text = _chat(c, msgs, temperature, max_tokens)
        try:
            obj = _parse(text)
            err = check(obj) if check else None
        except Exception as e:                                       # noqa: BLE001
            obj, err = None, f"that was not valid JSON ({e})"
        if not err: return obj
        msgs = msgs + [{"role": "assistant", "content": text}, {"role": "user", "content": f"Problem: {err}. Reply again with ONLY the corrected JSON object."}]
    raise LLMError(f"model could not produce a valid answer: {err}")


def ask_about_image(c, png: bytes, text, temperature=0.1, max_tokens=700, json_mode=False):
    """One question about one picture to the local vision-capable model. Returns the answer text (JSON text when json_mode)."""
    key = open(os.path.expanduser(c["keyfile"])).read().strip()
    body = {"model": c["model"], "temperature": temperature, "max_tokens": max_tokens, "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}, {"type": "text", "text": text}]}]}
    if json_mode: body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(c["url"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return re.sub(r"<think>.*?</think>", "", json.loads(r.read())["choices"][0]["message"]["content"], flags=re.S).strip()
    except Exception as e:                                           # noqa: BLE001
        raise LLMError(f"local vision call failed: {e}")
