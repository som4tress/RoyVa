"""General mode: when no skill matches (or the matching skill is not built yet), RoyVa gets every tool the user may use, writes behind approval,
and a prompt to reason about paths, try one, verify and report, instead of refusing. Not a registry intent (the router never picks it):
it is built per user from the active intents that user may use, so scoped tools (mail) never leak to someone without the scope."""
from __future__ import annotations

from .models import Intent, Profile
from .registry import Registry

GENERAL_ID = "general"

STYLE = ("No specific skill matched this request, so work it out yourself with the tools you have. Think of the possible ways to do it, pick the most direct, "
         "try it, and if it fails or returns nothing useful try the next way. Read before you change anything and check the result after a change. "
         "For anything on this machine or another allowed one (memory, disks, logs, cron jobs, files) use the machine tools (to list cron jobs run exactly `crontab -l` and for timers exactly `systemctl list-timers --all`, with nothing added or piped, so they run outside the sandbox): run and remote_run read freely inside a read-only sandbox; if one fails with Read-only file system and a change is really needed, use run_approved or remote_run_approved. "
         "For Home Assistant things no device tool covers (areas, automations, scenes, renames) use ha_read to look up ids and ha_write to change them; to change an EXISTING automation, script or scene use ha_read kind config to get its id and version, then ha_edit with small edits (never retype the whole config). "
         "ha_write, ha_edit, run_approved and remote_run_approved show the owner an Approve/Deny prompt themselves, so call them directly: never ask for confirmation in plain text first, and do not stop to ask before calling them. "
         "In replies, put a link on its own line, never inside backticks, brackets or bold, and never with a character right after it. Say that something was changed only if the tool result says it was saved; a dry run or a refusal means nothing changed. "
         "Say you cannot do something only after you have tried, and then name what you tried and what is missing.")


def build(reg: Registry, usable: list[Intent]) -> Intent:
    """Union of the available tools of the given (already scope-filtered, active) intents. Writes are always confirmed."""
    tools: list[str] = []
    for i in usable:
        for t in i.profile.tools:
            spec = reg.tools.get(t)
            if spec is not None and spec.available and t not in tools:
                tools.append(t)
    for t in reg.tools.values():                                        # general-purpose doors (machine, ...) that no skill lists
        if t.door and t.available and t.id not in tools:
            tools.append(t.id)
    return Intent(
        id=GENERAL_ID, status="fallback",
        description="General requests that no specific skill covers; use any available tool.",
        examples=["general one", "general two", "general three", "general four", "general five"], negatives=["general neg one", "general neg two"],
        profile=Profile(tools=tools, context=["current_time", "home_map"], steps=12, write_policy="confirm", sticky=True, style=STYLE))
