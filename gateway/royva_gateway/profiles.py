"""Turn routed intents into what OpenCode needs: a tool grant (permission rules) and context text for the model."""
from __future__ import annotations

from .config import Settings
from .models import Intent
from .registry import Registry

PER_TURN_PROVIDERS = {"current_location", "current_time"}        # refreshed on every message (the user moves); never cached per session

PROVIDER_TEXT = {
    # Static placeholders; real generators (home map from HA registry, speaker table, user profile) are separate tasks.
    "home_map": "Home layout: floors and areas are defined in Home Assistant. A floor (for example the upper or lower level) is not an area; "
                "for a question about a floor, query each of its areas, or fetch the whole home and filter, instead of passing the floor name as an area.",
    "speakers": "Speakers are Home Assistant media players; use their exact names.",
    "user_profile": "The user is a member of the household. Their email is Gmail.",
}


def context_text(provider: str, settings: Settings) -> str:
    if provider in settings.dynamic_context:                   # generated from Home Assistant at startup
        return settings.dynamic_context[provider]
    if provider == "home_location":
        loc = settings.home_location or "unknown (ask the user once for their city if a location is needed)"
        return f"Home location: {loc}."
    return PROVIDER_TEXT[provider]


def capability_hint(reg: Registry, intents: list[Intent]) -> str:
    """One sentence per intent about what its tools cover; this is the 'targeted steering' that fixed refusals in the replay test."""
    return " ".join(f"{i.description}" for i in intents)


def style_hint(intents: list[Intent]) -> str:
    return " ".join(i.profile.style for i in intents if i.profile.style)


def grants(reg: Registry, intents: list[Intent]) -> dict[str, str]:
    """tool id -> 'allow' | 'ask' for the union of a session's intents. Safety model:
    read tools are allowed; write/external tools are allowed only when every intent granting them is 'auto', otherwise 'ask'
    (OpenCode raises a permission request, which the bridge surfaces as /approve or /deny). A write tool inside a read_only intent is refused outright."""
    out: dict[str, str] = {}
    for i in intents:
        for t in i.profile.tools:
            spec = reg.tools.get(t)
            if spec is None or not spec.available:
                continue
            if spec.risk != "read" and i.profile.write_policy == "read_only":
                continue
            eff = "allow" if (spec.risk == "read" or i.profile.write_policy == "auto") else "ask"
            out[t] = "ask" if "ask" in (out.get(t), eff) else "allow"
    return out


def permissions(reg: Registry, grant_map: dict[str, str], settings: Settings) -> list[dict]:
    """Session-level rules. They are evaluated after the agent's rules and the last match wins, so these open exactly the granted tools."""
    rules = [{"action": reg.tools[t].action, "resource": "*", "effect": eff} for t, eff in grant_map.items()
             if reg.tools[t].action not in settings.never_grant]
    rules += [{"action": a, "resource": "*", "effect": "deny"} for a in settings.never_grant]      # belt and braces
    return rules


def step_cap(intents: list[Intent], default: int = 6) -> int:
    return max([i.profile.steps for i in intents] or [default])


COMBINED = ("This request combines several capabilities ({names}). Complete every part, in order: gather what is needed first, then deliver it the way the user asked "
            "(for example spoken or played on a speaker) by actually running that action, instead of only replying in text. Text is just the default delivery.")


def now_text(now=None) -> str:
    """The model has no clock: without this it assumes its training year (e.g. summarising 'this month's news' from a year ago)."""
    from datetime import datetime
    now = (now or datetime.now()).astimezone()
    return (f"Right now it is {now:%A %-d %B %Y}, {now:%H:%M} ({now.tzname()}). Use this date for 'today', 'tonight', 'this week', 'this month' and "
            f"for any news, price, forecast or schedule lookup (search for the current year, never an older one).")


def prompt_text(user_text: str, new_context: list[str], hint: str, settings: Settings, unsupported: list[str],
                per_turn: dict | None = None, style: str = "", combined: list[str] | None = None) -> str:
    parts = []
    texts = []
    for p in new_context:
        t = (per_turn or {}).get(p) if p in PER_TURN_PROVIDERS else context_text(p, settings)
        if t:
            texts.append(t)
    if texts:
        parts.append("\n".join(texts))
    if hint:
        parts.append("What you can do for this request: " + hint)
    if combined and len(combined) > 1:
        parts.append(COMBINED.format(names=", ".join(c.replace("_", " ") for c in combined)))
    if style:
        parts.append("Answer style: " + style)
    if unsupported:
        parts.append("Part of this request is not supported yet (" + "; ".join(unsupported) + "). Say so plainly for that part.")
    if not parts:
        return user_text
    return "<context>\n" + "\n".join(parts) + "\n</context>\n\n" + user_text
