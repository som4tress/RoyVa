"""General mode: when no skill matches (or the matching skill is not built yet), RoyVa gets every tool the user may use, writes behind approval,
and a prompt to reason about paths, try one, verify and report, instead of refusing. Not a registry intent (the router never picks it):
it is built per user from the active intents that user may use, so scoped tools (mail) never leak to someone without the scope."""
from __future__ import annotations

from .models import Intent, Profile
from .registry import Registry

GENERAL_ID = "general"

STYLE = ("No specific skill matched this request, so work it out yourself with the tools you have. Think of the possible ways to do it, pick the most direct, "
         "try it, and if it fails or returns nothing useful try the next way. Read before you change anything and check the result after a change. "
         "For Home Assistant things no device tool covers (areas, automations, scenes, renames) use ha_read to look up ids and ha_write to change them. "
         "Anything that changes something will ask the user for approval first; say plainly what you are about to do. "
         "Say you cannot do something only after you have tried, and then name what you tried and what is missing.")


def build(reg: Registry, usable: list[Intent]) -> Intent:
    """Union of the available tools of the given (already scope-filtered, active) intents. Writes are always confirmed."""
    tools: list[str] = []
    for i in usable:
        for t in i.profile.tools:
            spec = reg.tools.get(t)
            if spec is not None and spec.available and t not in tools:
                tools.append(t)
    return Intent(
        id=GENERAL_ID, status="fallback",
        description="General requests that no specific skill covers; use any available tool.",
        examples=["general one", "general two", "general three", "general four", "general five"], negatives=["general neg one", "general neg two"],
        profile=Profile(tools=tools, context=["current_time", "home_map"], steps=12, write_policy="confirm", sticky=True, style=STYLE))
