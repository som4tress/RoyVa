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
    assert d.compare("rest", "POST", "/api/config/automation/config/1", {}, lambda p: None)["available"] is False
    assert d.compare("rest", "POST", "/api/states/x", {}, lambda p: {})["available"] is False


def test_diff_endpoint_exists_and_reports_unavailable_for_other_paths(tmp_path):
    from test_app import client
    c, _ = client(tmp_path)
    r = c.post("/v1/diff", json={"kind": "rest", "method": "POST", "path": "/api/states/x", "params": {}})
    assert r.status_code == 200 and r.json()["available"] is False
