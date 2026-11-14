"""Small, exact edits to a saved Home Assistant config item (automation, script, scene), built by code instead of retyped by the model.

Shared by two processes that must agree: the gateway (builds the preview on the approval card) and the ha-api tool server (builds the same result again and saves it).
Standard library only; no Home Assistant access here: callers pass the stored config in and, optionally, a render function for templates.

An edit is {"path": "variables.notification_message", "op": "append" | "prepend" | "replace" | "set", ...}:
  append / prepend: "text"          the target must exist and be a string
  replace:          "find", "text"  `find` must occur exactly once in the target string
  set:              "value"         replaces an existing value (any JSON), or adds a new key inside an existing mapping below the top level
Paths are dotted, lists by index: "actions.1.then.0.data.message". The top-level set of keys never changes and "id" is never edited.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Optional

CONFIG_DOMAINS = ("automation", "script", "scene")
OPS = ("append", "prepend", "replace", "set")
MAX_EDITS = 20
MAX_TEXT = 20_000
TEMPLATE_MARK = re.compile(r"\{[{%]")


class EditError(ValueError):
    """The edit cannot be applied exactly as written. The message is meant for the model and the owner."""


def config_path(domain: str, item_id: str) -> str:
    if domain not in CONFIG_DOMAINS:
        raise EditError(f"domain must be one of {', '.join(CONFIG_DOMAINS)}")
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", str(item_id or "")):
        raise EditError("id must be the item's id as returned by ha_read kind config")
    return f"/api/config/{domain}/config/{item_id}"


def version(cfg: Any) -> str:
    """Fingerprint of a stored config. The tool refuses to save if the stored config has changed since the version the model (and the card) saw."""
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def _steps(path: Any) -> list:
    if isinstance(path, list):
        parts = path
    elif isinstance(path, str) and path.strip():
        parts = path.strip().split(".")
    else:
        raise EditError("each edit needs a path such as variables.notification_message")
    if not parts or any(p == "" for p in parts):
        raise EditError(f"bad path {path!r}")
    return [int(p) if isinstance(p, str) and p.isdigit() else p for p in parts]


def _child(node: Any, key: Any, shown: str) -> Any:
    if isinstance(node, dict) and isinstance(key, (str, int)) and str(key) in node:
        return node[str(key)]
    if isinstance(node, list) and isinstance(key, int) and 0 <= key < len(node):
        return node[key]
    raise EditError(f"nothing at {shown}")


def _locate(cfg: Any, steps: list, shown: str):
    """(container, key) of the value at the path, which must exist."""
    node = cfg
    for k in steps[:-1]:
        node = _child(node, k, shown)
    _child(node, steps[-1], shown)
    return node, (steps[-1] if isinstance(node, list) else str(steps[-1]))


def _strings(value: Any, label: str):
    """Every string inside a value (nested lists/dicts too) with its path, so template text hidden in a `set` value is still checked."""
    if isinstance(value, str):
        yield label, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(v, f"{label}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _strings(v, f"{label}.{i}")


def _clip(text: str, n: int = 80) -> str:
    text = text.replace("\n", "\\n")
    return text if len(text) <= n else text[: n - 1] + "…"


def apply_edits(cfg: dict, edits: Any) -> dict:
    """Returns {"config": new config, "changes": [one line per edit], "templates": [{"path", "text"}]}. Raises EditError; never modifies `cfg`."""
    if not isinstance(cfg, dict):
        raise EditError("the stored config is not a JSON object")
    if not isinstance(edits, list) or not edits:
        raise EditError("edits must be a non-empty list")
    if len(edits) > MAX_EDITS:
        raise EditError(f"at most {MAX_EDITS} edits per call")
    new = json.loads(json.dumps(cfg))
    changes, templates = [], []
    for n, e in enumerate(edits, 1):
        if not isinstance(e, dict):
            raise EditError(f"edit {n} must be an object")
        op, shown = e.get("op"), e.get("path")
        if op not in OPS:
            raise EditError(f"edit {n}: op must be one of {', '.join(OPS)}")
        steps = _steps(shown)
        label = shown if isinstance(shown, str) else ".".join(map(str, shown))
        if steps[0] == "id":
            raise EditError("the id cannot be edited")
        if op == "set" and len(steps) > 1 and not _exists(new, steps[:-1]):
            raise EditError(f"edit {n}: nothing at {'.'.join(map(str, steps[:-1]))}")
        if op == "set" and "value" not in e:
            raise EditError(f"edit {n}: set needs a value")
        if op == "set":
            parent = new if len(steps) == 1 else _resolve(new, steps[:-1])
            key = steps[-1]
            if isinstance(parent, dict):
                if len(steps) == 1 and str(key) not in parent:
                    raise EditError(f"edit {n}: {label} is not an existing top-level key (the top-level keys never change)")
                old = parent.get(str(key), "<new key>")
                parent[str(key)] = e["value"]
            elif isinstance(parent, list) and isinstance(key, int) and 0 <= key < len(parent):
                old = parent[key]
                parent[key] = e["value"]
            else:
                raise EditError(f"edit {n}: cannot set {label}")
            value = e["value"]
            whole = isinstance(old, (dict, list)) and isinstance(value, (dict, list))
            changes.append(f"set {label}{' (replaces a whole section)' if whole else ''}: {_clip(json.dumps(old) if not isinstance(old, str) else old)} -> {_clip(json.dumps(value) if not isinstance(value, str) else value)}")
            templates.extend({"path": where, "text": text} for where, text in _strings(value, label) if TEMPLATE_MARK.search(text))
            continue
        parent, key = _locate(new, steps, label)
        current = parent[key]
        if not isinstance(current, str):
            raise EditError(f"edit {n}: {label} is not text, so {op} cannot be used on it (use set)")
        text = e.get("text")
        if not isinstance(text, str) or not text or len(text) > MAX_TEXT:
            raise EditError(f"edit {n}: {op} needs a non-empty text")
        if op == "replace":
            find = e.get("find")
            if not isinstance(find, str) or not find:
                raise EditError(f"edit {n}: replace needs the text to find")
            hits = current.count(find)
            if hits != 1:
                raise EditError(f"edit {n}: the text to find occurs {hits} times in {label} (it must be exactly once); use a longer piece of text")
            updated = current.replace(find, text, 1)
        elif op == "append":
            updated = current + text
        else:
            updated = text + current
        parent[key] = updated
        changes.append(f"{op} {label}: {_clip(text)}")
        if TEMPLATE_MARK.search(text):
            templates.append({"path": label, "text": text})
    if set(new) != set(cfg):
        raise EditError("an edit may not add or remove a top-level key")
    return {"config": new, "changes": changes, "templates": templates}


def _resolve(node: Any, steps: list):
    for k in steps:
        node = _child(node, k, ".".join(map(str, steps)))
    return node


def _exists(node: Any, steps: list) -> bool:
    try:
        _resolve(node, steps)
        return True
    except EditError:
        return False


UNDEFINED_NAME = re.compile(r"'(\w+)' is undefined")
LINK_THEN_PUNCT = re.compile(r"https?://\S*[.,;:!?)\]}'\"]+(?=\s|$)")


def _render_with_placeholders(text: str, render: Callable[[str], dict]):
    """A piece of template that uses the automation's own variables (current, decision, trigger...) cannot render alone. Give each such name an empty
    placeholder and try again, so the piece can still be rendered and its output read. Returns (result, [placeholder names])."""
    names: list = []
    r: dict = {}
    for _ in range(8):
        r = render("".join("{% set " + n + " = {} %}" for n in names) + text)
        if r.get("ok"):
            return r, names
        m = UNDEFINED_NAME.search(str(r.get("error", "")))
        if not m or m.group(1) in names:
            return r, names
        names.append(m.group(1))
    return r, names


def check_templates(templates: list, render: Optional[Callable[[str], dict]]) -> dict:
    """Render each inserted piece of template on its own through `render(text) -> {"ok": bool, "text"|"error": str}`.
    A piece that refers to variables that only exist inside the automation (trigger, current...) cannot be rendered alone: that is reported, not blamed.
    Anything else that fails to render will fail for real: that is a problem."""
    out, problems, warnings = [], [], []
    for t in templates:
        if render is None:
            out.append({**t, "status": "skipped"})
            continue
        try:
            r, stubs = _render_with_placeholders(t["text"], render)
        except Exception as exc:                                      # noqa: BLE001
            r, stubs = {"ok": False, "error": str(exc)[:200]}, []
        if r.get("ok") and LINK_THEN_PUNCT.search(str(r.get("text", ""))):
            warnings.append(f"a link in the text added at {t['path']} is followed by a punctuation character, which becomes part of the link when it is tapped")
        if r.get("ok") and not str(r.get("text", "")).strip():
            # Renders fine but to nothing: legal, yet usually means the entity or attribute it reads does not exist (an 'ok' that shows blank is not a pass).
            out.append({**t, "status": "empty", "rendered": ""})
            warnings.append(f"the text added at {t['path']} renders to nothing right now: if that is not intended, the sensor or attribute it reads may not exist (read its real state first)")
        elif r.get("ok"):
            out.append({**t, "status": "ok", "rendered": str(r.get("text", ""))[:300], **({"placeholders": stubs} if stubs else {})})
        elif re.search(r"undefined", str(r.get("error", "")), re.I):
            out.append({**t, "status": "needs_context", "error": str(r.get("error", ""))[:200]})
        else:
            out.append({**t, "status": "error", "error": str(r.get("error", ""))[:300]})
            problems.append(f"the template added at {t['path']} does not render: {str(r.get('error', ''))[:200]}")
    return {"renders": out, "problems": problems, "warnings": warnings}


def plan(stored: dict, expected_version: str, edits: Any, render: Optional[Callable[[str], dict]] = None) -> dict:
    """Everything both the card and the save need: raises EditError for a stale version or an edit that cannot be applied.
    Returns {"config", "changes", "renders", "problems", "warnings"}. A non-empty "problems" means: do not save; warnings are shown but do not block."""
    if str(expected_version or "") != version(stored):
        raise EditError("the item changed since it was read (version mismatch): read it again with ha_read kind config and redo the edit")
    result = apply_edits(stored, edits)
    checked = check_templates(result["templates"], render)
    return {"config": result["config"], "changes": result["changes"], **checked}
