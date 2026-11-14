"""Approval-card diff: structural, generic, short, and only for stored config the gateway can read back."""
from royva_gateway import diffing as d

OLD = {"id": "1", "alias": "A", "variables": {"msg": "Battery {{ b }}%", "n": 1}, "actions": [{"service": "notify.x", "data": {"message": "hi"}}]}


def test_identical_config_has_no_changes_and_the_stored_id_is_ignored():
    new = {k: v for k, v in OLD.items() if k != "id"}
    r = d.json_diff(OLD, new)
    assert r["lines"] == [] and r["unchanged"] > 0


def test_added_removed_and_changed_fields_are_listed():
    new = {"alias": "A", "variables": {"msg": "Battery {{ b }}% map", "n": 1, "map": "x"}, "actions": [{"service": "notify.x", "data": {"message": "hi"}}], "mode": "single"}
    lines = d.json_diff(OLD, new)["lines"]
    assert any(l.startswith("+ variables.map") for l in lines) and any(l.startswith("+ mode") for l in lines)
    assert any(l.startswith("~ variables.msg") for l in lines) and len(lines) == 3


def test_long_template_edit_shows_only_the_changed_part():
    old = {"t": "A" * 400 + "OLD" + "B" * 400}
    new = {"t": "A" * 400 + "NEW" + "B" * 400}
    (line,) = d.json_diff(old, new)["lines"]
    assert "'OLD' -> 'NEW'" in line and len(line) < 200


def test_only_rest_saves_under_api_config_are_diffable():
    assert d.diffable("rest", "POST", "/api/config/automation/config/1")
    for bad in [("ws", "POST", "/api/config/automation/config/1"), ("rest", "DELETE", "/api/config/automation/config/1"), ("rest", "POST", "/api/services/light/turn_on"), ("rest", "POST", "/api/config/../states")]:
        assert not d.diffable(*bad)


def test_compare_uses_the_stored_copy_and_degrades_quietly():
    ok = d.compare("rest", "POST", "/api/config/automation/config/1", {"alias": "B"}, lambda p: {"alias": "A"})
    assert ok["available"] and ok["lines"] == ["~ alias: 'A' -> 'B'"]
    nothing = d.compare("rest", "POST", "/api/config/automation/config/1", {}, lambda p: None)
    assert nothing["available"] and nothing["failed"]
    assert d.compare("rest", "POST", "/api/states/x", {}, lambda p: {})["available"] is False


def test_diff_endpoint_exists_and_reports_unavailable_for_other_paths(tmp_path):
    from test_app import client
    c, _ = client(tmp_path)
    r = c.post("/v1/diff", json={"kind": "rest", "method": "POST", "path": "/api/states/x", "params": {}})
    assert r.status_code == 200 and r.json()["available"] is False


def test_plural_and_singular_section_names_are_not_a_change_and_trace_is_ignored():
    from royva_gateway import diffing
    old = {"id": "1", "alias": "A", "triggers": [{"x": 1}], "conditions": [], "actions": [{"y": 2}], "trace": {"stored_traces": 5}}
    new = {"alias": "A", "trigger": [{"x": 1}], "condition": [], "action": [{"y": 2}]}
    assert diffing.json_diff(old, new)["lines"] == []
    new["action"] = [{"y": 3}]
    assert [l for l in diffing.json_diff(old, new)["lines"] if "actions" in l]


def test_edit_preview_uses_the_same_rules_as_the_tool_server():
    from royva_gateway import diffing
    stored = {"id": "1", "alias": "A", "variables": {"msg": "Parked."}}
    ce = diffing._config_edit()
    args = {"domain": "automation", "id": "1", "version": ce.version(stored), "edits": [{"op": "append", "path": "variables.msg", "text": " {{ 1 }}"}]}
    out = diffing.preview_edit(args, lambda p: stored, lambda t: {"ok": True, "text": "https://maps?q=1,2"})
    assert out["ok"] and len(out["lines"]) == 1 and "variables.msg" in out["lines"][0]
    assert out["renders"][0]["status"] == "ok"
    stale = diffing.preview_edit({**args, "version": "old"}, lambda p: stored, None)
    assert not stale["ok"] and "changed since" in stale["problem"]
    unreadable = diffing.preview_edit(args, lambda p: None, None)
    assert not unreadable["ok"] and "could not read" in unreadable["problem"]
    bad = diffing.preview_edit(args, lambda p: stored, lambda t: {"ok": False, "error": "from_json got invalid input"})
    assert not bad["ok"] and "does not render" in bad["problem"] and bad["lines"]          # the diff is still shown, Approve is not offered


def test_a_long_string_changed_at_the_start_and_the_end_lists_both_places():
    mid = "x" * 300
    old = {"m": mid}
    new = {"m": "{% set gps = 1 %}" + mid + " Map: https://maps?q=1,2"}
    (line,) = d.json_diff(old, new)["lines"]
    assert "2 places" in line and "{% set gps = 1 %}" in line and "Map: https://maps?q=1,2" in line and len(line) < 400
