"""ha_api door: what counts as a read, what is refused outright, protected devices, dry run. Fakes only: no Home Assistant call is made."""
import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("ha_api", Path(__file__).resolve().parents[2] / "mcp" / "ha" / "ha_api.py")
ha = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ha)


def test_reads_are_recognised_and_writes_are_sent_to_the_approval_tool():
    for t in ("config/device_registry/list", "config/area_registry/list", "get_states", "config/entity_registry/get", "logbook/get_events", "get_services"):
        assert ha.check_read("ws", t) is None, t
    for t in ("config/device_registry/update", "config/area_registry/create", "call_service", "config/entity_registry/remove", "fire_event"):
        assert "ha_write" in ha.check_read("ws", t), t
    assert ha.check_read("rest", "/api/states") is None
    assert "GET" in ha.check_read("rest", "/api/services/light/turn_on", "POST")
    assert ha.check_read("rest", "/etc/passwd") is not None


def test_secrets_and_streams_refused_in_both_tools():
    for t in ("auth/current_user", "auth/long_lived_access_token", "config/auth_provider/homeassistant/list", "subscribe_events"):
        assert ha.check_read("ws", t) and ha.check_write("ws", t, "POST", {})


def test_read_tool_never_calls_write_paths():
    calls = []
    out = ha.ha_read({"kind": "ws", "type": "config/device_registry/update", "params": {"device_id": "x", "area_id": "y"}}, ws=lambda *a: calls.append(a))
    assert "error" in out and not calls


def test_write_runs_and_reports_the_exact_call(monkeypatch):
    monkeypatch.setattr(ha, "DRY_FLAG", Path("/nonexistent/dry"))
    monkeypatch.delenv("ROYVA_DRY_RUN", raising=False)
    seen = []
    out = ha.ha_write({"kind": "ws", "type": "config/device_registry/update", "params": {"device_id": "d1", "area_id": "master_bedroom"}},
                      ws=lambda t, p: seen.append((t, p)) or {"ok": 1})
    assert seen == [("config/device_registry/update", {"device_id": "d1", "area_id": "master_bedroom"})] and out["done"]["target"] == "config/device_registry/update"


def test_dry_run_changes_nothing(monkeypatch):
    monkeypatch.setenv("ROYVA_DRY_RUN", "1")
    out = ha.ha_write({"kind": "rest", "path": "/api/config/automation/config/x", "params": {"alias": "t"}}, rest=lambda *a: 1 / 0)
    assert out["dry_run"] and "DRY RUN" in out["did"]


def test_protected_device_refused_in_a_multi_target_change(monkeypatch):
    monkeypatch.setenv("ROYVA_PROTECTED_DEVICES", "Shivi Linux Box")
    bad = ha.check_write("rest", "/api/services/switch/turn_off", "POST", {"entity_id": ["switch.shivi_linux_box", "light.kitchen"]})
    assert bad and "protected" in bad
    assert ha.check_write("rest", "/api/services/switch/turn_off", "POST", {"entity_id": "switch.shivi_linux_box"}) is None      # alone: allowed (the owner approves it)


def test_big_results_are_capped():
    big = ha._cap({"x": "a" * 50000})
    assert big["truncated"] and len(big["first_chars"]) == ha.MAX_OUT


def test_list_results_are_narrowed_on_the_server():
    devices = [{"id": f"d{i}", "name": "Lamp %d" % i, "area_id": None, "junk": "x" * 500} for i in range(200)] + [{"id": "target", "name": "HAP-603WF-Bedroom", "area_id": None, "junk": "y" * 500}]
    out = ha.ha_read({"kind": "ws", "type": "config/device_registry/list", "contains": "hap-603wf", "fields": ["id", "name", "area_id"]}, ws=lambda *a: devices)
    assert out["result"] == {"matched": 1, "shown": 1, "items": [{"id": "target", "name": "HAP-603WF-Bedroom", "area_id": None}]}
    whole = ha.ha_read({"kind": "ws", "type": "config/device_registry/list"}, ws=lambda *a: devices)
    assert whole["result"]["matched"] == 201 and whole["result"]["shown"] < 50 and "contains" in whole["result"]["hint"]      # never the whole list by default
    assert "contains" in ha._cap({"x": "a" * 50000})["hint"]


def test_home_assistant_refusal_reason_reaches_the_model():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mcp" / "ha"))
    import ha_ws
    text = ha_ws.failure_text({"success": False, "error": {"code": "invalid_format", "message": "extra keys not allowed @ data['foo']"}})
    assert "invalid_format" in text and "extra keys not allowed" in text
    assert ha_ws.failure_text({"error": {"code": "not_found"}}).endswith("not_found")


def test_params_cannot_override_command_type_or_id():
    assert ha.check_read("ws", "config/device_registry/list", "GET", {"type": "config/device_registry/remove_config_entry"})
    assert ha.check_read("ws", "config/device_registry/list", "GET", {"id": 5})
    assert ha.check_read("ws", "config/device_registry/list", "GET", {"limit": 5}) is None
    assert ha.check_write("ws", "config/device_registry/update", "GET", {"type": "x"})


def test_a_stored_automation_can_be_sent_back_with_its_own_id_but_no_other_id(monkeypatch):
    """First hop of the Ford edit: GET returns the config with its id; the natural read-modify-write sends it back. Same id on its own path is fine."""
    monkeypatch.setenv("ROYVA_DRY_RUN", "1")
    path = "/api/config/automation/config/1792893750683"
    stored = {"id": "1792893750683", "alias": "A", "actions": []}
    out = ha.ha_write({"kind": "rest", "path": path, "params": stored}, rest=lambda *a: 1 / 0)
    assert out.get("dry_run") and "error" not in out
    assert "id" in ha.ha_write({"kind": "rest", "path": path, "params": {**stored, "id": "other"}})["error"]
    assert "id" in ha.ha_write({"kind": "rest", "path": "/api/services/light/turn_on", "params": {"id": "1792893750683"}})["error"]
    assert "type" in ha.ha_write({"kind": "rest", "path": path, "params": {**stored, "type": "x"}})["error"]
    assert ha.check_write("ws", "config/device_registry/update", "POST", {"id": 5})           # websocket: id is still the command id, never allowed


def test_ws_command_type_wins_over_params():
    sent = {}
    class Fake:
        @staticmethod
        def call(url, token, cmds, timeout=15):
            sent["cmd"] = cmds[0]
            return {1: "ok"}
    ha_ws_real = ha.ha_ws
    ha.ha_ws = Fake
    ha._auth = lambda: ("ws://x", "t", "http://x")
    try:
        ha._ws("config/device_registry/list", {"type": "evil"})
    finally:
        ha.ha_ws = ha_ws_real
    assert sent["cmd"]["type"] == "config/device_registry/list"


def test_a_large_automation_write_is_not_refused_for_size(monkeypatch):
    """The 2026-11-13 Ford edit was refused at 3000 characters. Size is now handled by the approval card (full call attached); only a sanity ceiling remains."""
    monkeypatch.setenv("ROYVA_DRY_RUN", "1")
    big = {"alias": "t", "variables": {"decision": "x" * 6000}}
    out = ha.ha_write({"kind": "rest", "path": "/api/config/automation/config/x", "params": big}, rest=lambda *a: 1 / 0)
    assert out.get("dry_run") and "error" not in out
    huge = {"alias": "t", "variables": {"decision": "x" * 120_000}}
    assert "larger than" in ha.ha_write({"kind": "rest", "path": "/api/config/automation/config/x", "params": huge})["error"]


def test_config_item_is_found_by_name_with_its_id_resolved_server_side():
    states = [{"entity_id": "automation.ford_update", "state": "on", "attributes": {"friendly_name": "Ford Update", "id": "1792893750683"}},
              {"entity_id": "automation.other", "state": "on", "attributes": {"friendly_name": "Other", "id": "2"}},
              {"entity_id": "script.ford_update_now", "state": "off", "attributes": {"friendly_name": "Ford update now"}}]
    seen = []
    def rest(method, path, body=None):
        seen.append((method, path))
        return {"http_status": 200, "body": states if path == "/api/states" else {"id": "1792893750683", "alias": "Ford Update"}}
    out = ha.ha_read({"kind": "config", "domain": "automation", "name": "ford update"}, rest=rest)
    assert out["id"] == "1792893750683" and out["read"]["body"]["alias"] == "Ford Update"
    assert seen == [("GET", "/api/states"), ("GET", "/api/config/automation/config/1792893750683")]          # reads only
    scr = ha.ha_read({"kind": "config", "domain": "script", "name": "ford update"}, rest=rest)
    assert scr["config_path"] == "/api/config/script/config/ford_update_now"          # scripts are keyed by object id
    two = ha.ha_read({"kind": "config", "domain": "automation", "name": ""}, rest=rest)
    assert len(two["matches"]) == 2 and "read" not in two
    assert "no automation" in ha.ha_read({"kind": "config", "domain": "automation", "name": "zzz"}, rest=rest)["error"]
    assert "domain" in ha.ha_read({"kind": "config", "domain": "light", "name": "x"}, rest=rest)["error"]
