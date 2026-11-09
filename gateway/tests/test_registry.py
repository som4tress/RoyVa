import copy
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from royva_gateway import registry
from royva_gateway.models import AskRequest, AskResponse, Intent, SessionState, ToolSpec

REG = Path(__file__).resolve().parent.parent / "registry"


def seed(tmp_path: Path) -> Path:
    dst = tmp_path / "registry"
    shutil.copytree(REG, dst)
    return dst


def edit_intent(root: Path, name: str, fn):
    p = root / "intents" / f"{name}.json"
    d = json.loads(p.read_text())
    fn(d)
    p.write_text(json.dumps(d))


# ------------------------------------------------------------------ the real registry loads
def test_seed_registry_loads():
    r = registry.load(REG)
    assert {"home_state", "mail_read", "web_lookup"} <= {i.id for i in r.active()}
    assert len(r.intents) == 11
    assert all(i.status != "active" for i in r.intents.values() if any(not r.tools[t].available for t in i.profile.tools))


def test_actions_map_to_opencode_names():
    r = registry.load(REG)
    assert r.actions_for(["ha.get_live_context", "web.search"]) == ["home-assistant_homeassistant__GetLiveContext", "websearch"]


# ------------------------------------------------------------------ guardrails reject bad intents
def test_unknown_tool_rejected(tmp_path):
    root = seed(tmp_path)
    edit_intent(root, "home_state", lambda d: d["profile"]["tools"].append("ha.nuke_house"))
    with pytest.raises(registry.RegistryError) as e:
        registry.load(root)
    assert "not in the catalog" in str(e.value)


def test_read_only_cannot_hold_write_tool(tmp_path):
    root = seed(tmp_path)
    edit_intent(root, "home_state", lambda d: d["profile"]["tools"].append("ha.turn_off"))
    with pytest.raises(registry.RegistryError) as e:
        registry.load(root)
    assert "read_only" in str(e.value)


def test_active_cannot_use_unbuilt_tool(tmp_path):
    root = seed(tmp_path)
    edit_intent(root, "home_state", lambda d: d["profile"]["tools"].append("calendar.list_events"))
    with pytest.raises(registry.RegistryError) as e:
        registry.load(root)
    assert "not built yet" in str(e.value)


def test_agent_authored_write_intent_cannot_self_activate(tmp_path):
    root = seed(tmp_path)

    def make(d):
        d["status"] = "active"
        d["provenance"]["created_by"] = "agent"
        d["profile"]["tools"] = ["ha.get_live_context", "ha.turn_on"]
        d["profile"]["write_policy"] = "confirm"

    edit_intent(root, "home_control", make)
    with pytest.raises(registry.RegistryError) as e:
        registry.load(root)
    assert "approved_by" in str(e.value)
    # once a human approves, it loads
    edit_intent(root, "home_control", lambda d: d["provenance"].update(approved_by="somdutta"))
    assert "home_control" in registry.load(root).intents


def test_auto_policy_not_allowed_with_external_tools(tmp_path):
    root = seed(tmp_path)
    edit_intent(root, "media_playback", lambda d: (d["profile"]["tools"].append("ha.broadcast"), d["profile"].update(write_policy="auto")))
    with pytest.raises(registry.RegistryError) as e:
        registry.load(root)
    assert "auto" in str(e.value)


def test_example_cannot_also_be_negative(tmp_path):
    root = seed(tmp_path)
    edit_intent(root, "home_state", lambda d: d["negatives"].append(d["examples"][0]))
    with pytest.raises(registry.RegistryError):
        registry.load(root)


def test_same_example_in_two_intents_rejected(tmp_path):
    root = seed(tmp_path)
    shared = json.loads((root / "intents" / "home_state.json").read_text())["examples"][0]
    edit_intent(root, "calendar", lambda d: d["examples"].append(shared))
    with pytest.raises(registry.RegistryError) as e:
        registry.load(root)
    assert "appears in both" in str(e.value)


def test_unknown_field_rejected(tmp_path):
    root = seed(tmp_path)
    edit_intent(root, "home_state", lambda d: d.update(surprise=True))
    with pytest.raises(registry.RegistryError):
        registry.load(root)


def test_file_name_must_match_id(tmp_path):
    root = seed(tmp_path)
    (root / "intents" / "calendar.json").rename(root / "intents" / "cal.json")
    with pytest.raises(registry.RegistryError) as e:
        registry.load(root)
    assert "does not match file name" in str(e.value)


def test_all_problems_reported_together(tmp_path):
    root = seed(tmp_path)
    edit_intent(root, "home_state", lambda d: d["profile"]["tools"].append("ha.nope"))
    edit_intent(root, "mail_read", lambda d: d["profile"]["tools"].append("gmail.send_message"))
    with pytest.raises(registry.RegistryError) as e:
        registry.load(root)
    assert len(e.value.problems) >= 2


# ------------------------------------------------------------------ API contract
def test_reply_requires_session():
    with pytest.raises(ValidationError):
        AskRequest(text="and downstairs?", user="telegram:1", is_reply=True)
    assert AskRequest(text="hi", user="telegram:1").session_id is None


def test_response_roundtrip():
    r = AskResponse.model_validate({
        "session_id": "ses_1", "answer": "ok", "status": "done",
        "routing": {"trace_id": "rt_1", "mode": "continuation", "intents": ["home_state"], "confidence": 0.9,
                    "profile_tools": ["ha.get_live_context"]}})
    assert AskResponse.model_validate_json(r.model_dump_json()) == r


def test_confidence_bounds():
    with pytest.raises(ValidationError):
        AskResponse.model_validate({"session_id": "s", "answer": "x", "status": "done",
                                    "routing": {"trace_id": "t", "mode": "new", "intents": [], "confidence": 1.5, "profile_tools": []}})


def test_session_state_defaults():
    s = SessionState(session_id="ses_1", created_at="2026-11-07T15:40:00Z")
    assert s.tools == [] and s.busy is False and s.pending_confirmation is None


def test_tool_id_format():
    with pytest.raises(ValidationError):
        ToolSpec(id="BadId", action="x", server="s", risk="read", description="d")


def test_owner_policy_pins():
    """Owner decisions that must never change silently: device control is on and runs without approval; Gmail changes ask first."""
    intents = {p.stem: json.loads(p.read_text()) for p in (REG / "intents").glob("*.json")}
    assert intents["home_control"]["status"] == "active" and intents["home_control"]["profile"]["write_policy"] == "auto"
    assert intents["mail_manage"]["profile"]["write_policy"] == "confirm"
    for name in ("home_state", "home_history", "mail_read", "web_lookup"):
        assert intents[name]["profile"]["write_policy"] == "read_only"
