"""Load and cross-validate the tool catalog and intent registry. All problems are collected and reported together."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .models import Intent, ToolSpec


class RegistryError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("registry invalid:\n  - " + "\n  - ".join(problems))


@dataclass
class Registry:
    tools: dict[str, ToolSpec]
    intents: dict[str, Intent]
    router_examples: dict = field(default_factory=lambda: {"cross": [], "none": []})   # few-shot data for LLM routers

    def active(self) -> list[Intent]:
        return [i for i in self.intents.values() if i.status == "active"]

    def routable(self) -> list[Intent]:
        """Intents the router may choose from (candidates are shadow-only and handled elsewhere)."""
        return self.active()

    def actions_for(self, tool_ids: list[str]) -> list[str]:
        return [self.tools[t].action for t in tool_ids]


def check_intent(intent: Intent, tools: dict[str, ToolSpec]) -> list[str]:
    """Guardrails that need the catalog. Returns a list of problems (empty = fine)."""
    out: list[str] = []
    p = intent.profile
    for t in p.tools:
        if t not in tools:
            out.append(f"{intent.id}: tool '{t}' is not in the catalog")
    known = [tools[t] for t in p.tools if t in tools]
    risky = [t.id for t in known if t.risk in ("write", "external")]
    if p.write_policy == "read_only" and risky:
        out.append(f"{intent.id}: write_policy is read_only but profile includes write tools {risky}")
    if intent.status == "active":
        missing = [t.id for t in known if not t.available]
        if missing:
            out.append(f"{intent.id}: active intent uses tools that are not built yet {missing}")
    if intent.provenance.created_by == "agent" and intent.status == "active" and risky and not intent.provenance.approved_by:
        out.append(f"{intent.id}: agent-authored intent with write tools cannot be active without approved_by")
    if p.write_policy == "auto" and any(t.risk == "external" for t in known):
        out.append(f"{intent.id}: write_policy 'auto' is not allowed with external-risk tools (needs confirmation)")
    return out


def load(root: Path | str) -> Registry:
    root = Path(root)
    problems: list[str] = []

    tools: dict[str, ToolSpec] = {}
    try:
        raw = json.loads((root / "tools.json").read_text())
    except Exception as e:                                   # noqa: BLE001
        raise RegistryError([f"tools.json unreadable: {e}"])
    for i, item in enumerate(raw):
        try:
            spec = ToolSpec.model_validate(item)
        except ValidationError as e:
            problems.append(f"tools.json[{i}]: {e.errors()[0]['msg']} ({e.errors()[0]['loc']})")
            continue
        if spec.id in tools:
            problems.append(f"tools.json: duplicate tool id {spec.id}")
        tools[spec.id] = spec
    actions = [t.action for t in tools.values()]
    for a in {a for a in actions if actions.count(a) > 1}:
        problems.append(f"tools.json: action '{a}' appears in more than one tool")

    intents: dict[str, Intent] = {}
    for f in sorted((root / "intents").glob("*.json")):
        try:
            intent = Intent.model_validate_json(f.read_text())
        except ValidationError as e:
            for err in e.errors():
                problems.append(f"{f.name}: {err['msg']} at {'.'.join(str(x) for x in err['loc'])}")
            continue
        except Exception as e:                               # noqa: BLE001
            problems.append(f"{f.name}: unreadable ({e})")
            continue
        if intent.id != f.stem:
            problems.append(f"{f.name}: id '{intent.id}' does not match file name")
        if intent.id in intents:
            problems.append(f"{f.name}: duplicate intent id {intent.id}")
        problems += check_intent(intent, tools)
        intents[intent.id] = intent

    # Phrases must not be shared between intents (examples of one cannot be negatives-free duplicates of another).
    seen: dict[str, str] = {}
    for intent in intents.values():
        for s in intent.examples:
            k = s.lower()
            if k in seen and seen[k] != intent.id:
                problems.append(f"example '{s}' appears in both {seen[k]} and {intent.id}")
            seen.setdefault(k, intent.id)

    examples = {"cross": [], "none": []}
    ef = root / "router_examples.json"
    if ef.exists():
        try:
            raw = json.loads(ef.read_text())
            for item in raw.get("cross", []):
                ids = item.get("intents", [])
                if not str(item.get("text", "")).strip() or len(ids) < 2:
                    problems.append(f"router_examples.json: cross example needs text and at least two intents: {item!r:.60}")
                for i in ids:
                    if i not in intents:
                        problems.append(f"router_examples.json: unknown intent '{i}'")
            for t in raw.get("none", []):
                if not str(t).strip():
                    problems.append("router_examples.json: blank 'none' example")
            examples = {"cross": raw.get("cross", []), "none": raw.get("none", [])}
        except Exception as e:                                   # noqa: BLE001
            problems.append(f"router_examples.json unreadable: {e}")

    if problems:
        raise RegistryError(problems)
    return Registry(tools=tools, intents=intents, router_examples=examples)
