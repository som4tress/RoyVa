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
    miss = ha.ha_read({"kind": "config", "domain": "automation", "name": "zzz"}, rest=rest)
    assert "no automation" in miss["error"] and miss["all_names"] == ["Ford Update", "Other"] and "ask the owner" in miss["hint"]
    assert ha.ha_read({"kind": "config", "domain": "automation", "name": "update ford"}, rest=rest)["id"] == "1792893750683"      # word order does not matter
    assert "domain" in ha.ha_read({"kind": "config", "domain": "light", "name": "x"}, rest=rest)["error"]


def test_contains_inside_params_still_filters():
    items = [{"entity_id": "automation.a"}, {"entity_id": "light.b"}]
    out = ha.ha_read({"kind": "rest", "path": "/api/states", "params": {"contains": "automation."}}, rest=lambda *a: {"http_status": 200, "body": items})
    assert out["body"]["matched"] == 1


def test_put_to_a_config_item_is_sent_as_post(monkeypatch):
    monkeypatch.delenv("ROYVA_DRY_RUN", raising=False)
    monkeypatch.setattr(ha, "DRY_FLAG", Path("/nonexistent/dry"))
    seen = []
    out = ha.ha_write({"kind": "rest", "method": "PUT", "path": "/api/config/automation/config/1", "params": {"alias": "t"}}, rest=lambda m, p, b=None: seen.append(m) or {"http_status": 200, "body": {}})
    assert seen == ["POST"] and out["done"]["method"] == "POST"


# ---- ha_edit: small exact edits, rebuilt from what is stored right now
class FakeHA:
    def __init__(self, cfg, render_ok=True, save_status=200):
        self.cfg, self.calls, self.render_ok, self.save_status = cfg, [], render_ok, save_status

    def __call__(self, method, path, body=None):
        self.calls.append((method, path))
        if method == "GET":
            return {"http_status": 200, "body": json.loads(json.dumps(self.cfg))}
        if path == "/api/template":
            return {"http_status": 200, "body": "https://maps?q=1,2"} if self.render_ok else {"http_status": 400, "body": "ValueError: from_json got invalid input"}
        if self.save_status == 200:
            self.cfg = body
        return {"http_status": self.save_status, "body": {"result": "ok"}}


STORED = {"id": "17", "alias": "Ford", "triggers": [], "variables": {"msg": "Parked."}, "actions": []}


def _edit_args(**over):
    from_mod = ha.config_edit
    return {"domain": "automation", "id": "17", "version": from_mod.version(STORED), "edits": [{"op": "append", "path": "variables.msg", "text": " {{ 1 }}"}], **over}


def test_ha_edit_saves_the_edited_config_and_reads_it_back(monkeypatch):
    monkeypatch.delenv("ROYVA_DRY_RUN", raising=False)
    monkeypatch.setattr(ha, "DRY_FLAG", Path("/nonexistent/dry"))
    fake = FakeHA(STORED)
    out = ha.ha_edit(_edit_args(), rest=fake)
    assert out["saved"] is True and out["done"]["id"] == "17"
    assert fake.cfg["variables"]["msg"] == "Parked. {{ 1 }}" and fake.cfg["alias"] == "Ford" and fake.cfg["id"] == "17"
    assert ("POST", "/api/config/automation/config/17") in fake.calls


def test_ha_edit_refuses_without_saving(monkeypatch):
    monkeypatch.delenv("ROYVA_DRY_RUN", raising=False)
    monkeypatch.setattr(ha, "DRY_FLAG", Path("/nonexistent/dry"))
    for args, word in ((_edit_args(version="old"), "changed since"),
                       (_edit_args(edits=[{"op": "append", "path": "variable.msg", "text": "x"}]), "nothing at"),
                       (_edit_args(domain="light"), "domain")):
        fake = FakeHA(STORED)
        out = ha.ha_edit(args, rest=fake)
        assert word in out["error"] and not any(m == "POST" and p != "/api/template" for m, p in fake.calls), (args, out)
    broken = FakeHA(STORED, render_ok=False)
    out = ha.ha_edit(_edit_args(), rest=broken)
    assert "does not render" in out["error"] and not any(p.startswith("/api/config") and m == "POST" for m, p in broken.calls)


def test_ha_edit_dry_run_and_failed_save(monkeypatch):
    monkeypatch.setenv("ROYVA_DRY_RUN", "1")
    fake = FakeHA(STORED)
    out = ha.ha_edit(_edit_args(), rest=fake)
    assert out["dry_run"] and "DRY RUN" in out["did"] and fake.cfg == STORED
    monkeypatch.delenv("ROYVA_DRY_RUN")
    monkeypatch.setattr(ha, "DRY_FLAG", Path("/nonexistent/dry"))
    out = ha.ha_edit(_edit_args(), rest=FakeHA(STORED, save_status=500))
    assert out["saved"] is False and "did not accept" in out["error"]


def test_ha_edit_will_not_name_a_protected_device(monkeypatch):
    monkeypatch.setenv("ROYVA_PROTECTED_DEVICES", "Shivi Linux Box")
    out = ha.ha_edit(_edit_args(edits=[{"op": "append", "path": "variables.msg", "text": " switch.shivi_linux_box off"}]), rest=FakeHA(STORED))
    assert "protected" in out["error"]


def test_config_lookup_returns_the_version_needed_for_an_edit():
    states = [{"entity_id": "automation.ford", "state": "on", "attributes": {"friendly_name": "Ford", "id": "17"}}]
    out = ha.ha_read({"kind": "config", "domain": "automation", "name": "ford"}, rest=lambda m, p, b=None: {"http_status": 200, "body": states if p == "/api/states" else STORED})
    assert out["version"] == ha.config_edit.version(STORED) and "ha_edit" in out["next"]


def test_check_edit_reports_problems_to_the_model_and_saves_nothing():
    fake = FakeHA(STORED)
    ok = ha.ha_read({"kind": "check_edit", **{k: v for k, v in _edit_args().items()}}, rest=fake)
    assert ok["ok"] is True and ok["changes"] and "call ha_edit" in ok["next"]
    bad_path = ha.ha_read({"kind": "check_edit", **_edit_args(edits=[{"op": "append", "path": "variable.msg", "text": "x"}])}, rest=fake)
    assert bad_path["ok"] is False and "nothing at variable.msg" in bad_path["problem"]                # the 2026-11-14 slip, now fixable by the model itself
    stale = ha.ha_read({"kind": "check_edit", **_edit_args(version="old")}, rest=fake)
    assert stale["ok"] is False and "changed since" in stale["problem"]
    broken = ha.ha_read({"kind": "check_edit", **_edit_args()}, rest=FakeHA(STORED, render_ok=False))
    assert broken["ok"] is False and "does not render" in broken["problems"][0]
    assert all(m == "GET" or p == "/api/template" for m, p in fake.calls)                              # never a save


def test_a_big_config_keeps_the_fields_the_next_step_needs():
    big = {**STORED, "variables": {"msg": "x" * 40_000}}
    states = [{"entity_id": "automation.ford", "state": "on", "attributes": {"friendly_name": "Ford", "id": "17"}}]
    out = ha.ha_read({"kind": "config", "domain": "automation", "name": "ford"}, rest=lambda m, p, b=None: {"http_status": 200, "body": states if p == "/api/states" else big})
    assert out["version"] == ha.config_edit.version(big) and out["id"] == "17" and "check_edit" in out["next"] and out["read"].get("truncated")
