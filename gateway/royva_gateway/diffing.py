"""Compare a Home Assistant config write with what is saved now, so an approval card can show a short list of changes instead of a wall of JSON.
Generic: works on any JSON object saved under /api/config/ (automations, scripts, scenes...). Pure functions plus one guarded read."""
from __future__ import annotations

import json
from typing import Any

MAX_LINES = 200
IGNORED_TOP_KEYS = {"id", "trace"}   # a save is addressed by the path; the stored copy carries an id (and a trace setting) the write does not
ALIASES = {"trigger": "triggers", "condition": "conditions", "action": "actions"}      # Home Assistant accepts both spellings and means the same; do not show a rename as a change


def _canon(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {ALIASES.get(k, k): v for k, v in obj.items()}
    return obj


def _clip(text: str, n: int = 90) -> str:
    text = text.replace("\n", "\\n")
    return text if len(text) <= n else text[: n - 1] + "…"


def _change(old: str, new: str) -> str:
    """Show only the part of a long string that differs (common start and end trimmed, a little context kept)."""
    if len(old) <= 90 and len(new) <= 90:
        return f"{_clip(old)!r} -> {_clip(new)!r}"
    a = 0
    while a < min(len(old), len(new)) and old[a] == new[a]:
        a += 1
    b = 0
    while b < min(len(old), len(new)) - a and old[-1 - b] == new[-1 - b]:
        b += 1
    ctx = 30
    head = ("…" if a > ctx else "") + old[max(0, a - ctx):a]
    tail = old[len(old) - b: len(old) - b + ctx] + ("…" if b > ctx else "")
    o, n = old[a: len(old) - b], new[a: len(new) - b]
    return f"…{head}[{_clip(o, 160)!r} -> {_clip(n, 160)!r}]{tail}…"


def _walk(old: Any, new: Any, path: str, out: list[str], counts: dict) -> None:
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new)):
            if not path and k in IGNORED_TOP_KEYS:
                continue
            p = f"{path}.{k}" if path else str(k)
            if k not in old:
                out.append(f"+ {p}: {_clip(json.dumps(new[k]))}")
            elif k not in new:
                out.append(f"- {p} (removed)")
            else:
                _walk(old[k], new[k], p, out, counts)
        return
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for i, (a, b) in enumerate(zip(old, new)):
            _walk(a, b, f"{path}[{i}]", out, counts)
        return
    if old == new:
        counts["unchanged"] += 1
        return
    if isinstance(old, str) and isinstance(new, str):
        out.append(f"~ {path}: {_change(old, new)}")
    else:
        out.append(f"~ {path}: {_clip(json.dumps(old))} -> {_clip(json.dumps(new))}")


def json_diff(old: Any, new: Any) -> dict:
    out: list[str] = []
    counts = {"unchanged": 0}
    _walk(_canon(old), _canon(new), "", out, counts)
    return {"lines": out[:MAX_LINES] + ([f"… {len(out) - MAX_LINES} more"] if len(out) > MAX_LINES else []), "unchanged": counts["unchanged"]}


def diffable(kind: str, method: str, path: str) -> bool:
    """Only a REST save under /api/config/ has a stored version we can read back with a plain GET."""
    return kind == "rest" and str(method or "POST").upper() in ("POST", "PUT") and isinstance(path, str) and path.startswith("/api/config/") and ".." not in path


def compare(kind: str, method: str, path: str, params: dict, fetch) -> dict:
    """{'available': bool, 'lines': [...], 'unchanged': int}. fetch(path) -> stored JSON or None."""
    if not diffable(kind, method, path):
        return {"available": False, "lines": [], "unchanged": 0}
    stored = fetch(path)
    if not isinstance(stored, dict) or not isinstance(params, dict):
        return {"available": True, "failed": True, "lines": [], "unchanged": 0}      # a saveable path whose saved copy could not be read: say so, do not stay silent
    return {"available": True, **json_diff(stored, params)}


def _config_edit():
    import sys
    from pathlib import Path
    d = str(Path(__file__).resolve().parent.parent.parent / "mcp" / "ha")
    if d not in sys.path:
        sys.path.insert(0, d)
    import config_edit                                              # shared with the ha-api tool server: the card and the save must agree
    return config_edit


def preview_edit(args: dict, fetch, render) -> dict:
    """What an ha_edit call would do, for the approval card. Same code as the tool server runs at execution.
    {"ok": bool, "lines": [...changes vs saved...], "edits": [...one line per edit...], "renders": [...], "problem": str|None}.
    ok False means the call cannot be saved as written (stale version, bad path, template that fails): the card must not offer Approve."""
    ce = _config_edit()
    try:
        path = ce.config_path(str(args.get("domain") or ""), str(args.get("id") or ""))
        stored = fetch(path)
        if not isinstance(stored, dict):
            return {"ok": False, "problem": "could not read the saved config from Home Assistant", "lines": [], "edits": [], "renders": []}
        plan = ce.plan(stored, args.get("version"), args.get("edits"), render)
    except ce.EditError as exc:
        return {"ok": False, "problem": str(exc), "lines": [], "edits": [], "renders": []}
    problems = plan["problems"]
    return {"ok": not problems, "problem": "; ".join(problems) or None, "lines": json_diff(stored, plan["config"])["lines"],
            "edits": plan["changes"], "renders": plan["renders"]}
