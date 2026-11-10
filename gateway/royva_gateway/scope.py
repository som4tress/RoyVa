"""What the previous turn of a conversation acted on, read back from the session's own tool calls (nothing is guessed or hardcoded).
Injected into follow-ups so words like "everything", "the rest" or "those" resolve against it instead of the whole home."""
from __future__ import annotations

import json
from typing import Optional

from .runner import NON_TOOL_PARTS

MAX_CALLS = 12
MAX_VALUE = 60

RULE = ("Earlier in this conversation you called: {calls}. If the user's follow-up says everything, all, the rest, those, them or similar, "
        "it refers to exactly that scope, not the whole home, unless they name a different one.")


def _short(name: str) -> str:
    return name.rsplit("__", 1)[-1] if "__" in name else name


def _fmt(value) -> str:
    s = value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
    return s if len(s) <= MAX_VALUE else s[:MAX_VALUE - 1] + "…"


def last_turn_calls(rows: list[dict]) -> list[str]:
    """Tool calls (name + inputs) of the most recent exchange that used tools, completed ones only, de-duplicated, oldest first."""
    found: list[str] = []
    started = False
    for m in reversed(rows):
        if m.get("type") == "user":
            if started:
                break
            continue
        if m.get("type") != "assistant":
            continue
        calls = []
        for p in m.get("content") or []:
            if not p.get("type") or p["type"] in NON_TOOL_PARTS:
                continue
            st = p.get("state") or {}
            if st.get("status") != "completed":
                continue
            args = st.get("input") or {}
            calls.append(f"{_short(p.get('name', '?'))}(" + ", ".join(f"{k}={_fmt(v)}" for k, v in args.items()) + ")")
        if calls:
            started = True
            found = calls + found
    return list(dict.fromkeys(found))[:MAX_CALLS]


async def previous_scope(oc, session_id: str) -> Optional[str]:
    """One line for the prompt, or None. Never raises: a failure here must not break the turn."""
    try:
        calls = last_turn_calls(await oc.messages(session_id))
    except Exception:                                      # noqa: BLE001
        return None
    return RULE.format(calls="; ".join(calls)) if calls else None
