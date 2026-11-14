"""Exact edits to a stored automation/script/scene: what is allowed, what is refused, and that nothing else is touched."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("config_edit", Path(__file__).resolve().parents[2] / "mcp" / "ha" / "config_edit.py")
ce = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ce)

AUTOMATION = {"id": "1", "alias": "Ford", "triggers": [{"trigger": "state", "entity_id": "sensor.x"}], "conditions": [],
              "actions": [{"if": [{"condition": "template", "value_template": "{{ true }}"}], "then": [{"action": "notify.phone", "data": {"message": "{{ msg }}"}}]}],
              "variables": {"msg": "Parked. Battery: {{ 5 }}%.", "n": 3}, "mode": "queued"}


def edit(*edits, cfg=AUTOMATION):
    return ce.apply_edits(cfg, list(edits))


def test_append_changes_only_that_field_and_leaves_everything_else_identical():
    out = edit({"op": "append", "path": "variables.msg", "text": " Map: {{ 1 }}"})
    new = out["config"]
    assert new["variables"]["msg"] == "Parked. Battery: {{ 5 }}%. Map: {{ 1 }}"
    new["variables"]["msg"] = AUTOMATION["variables"]["msg"]
    assert new == AUTOMATION                                         # nothing else moved
    assert AUTOMATION["variables"]["msg"].endswith("%.")             # the input was not modified
    assert out["templates"] == [{"path": "variables.msg", "text": " Map: {{ 1 }}"}]


def test_prepend_replace_and_set():
    assert edit({"op": "prepend", "path": "alias", "text": "[x] "})["config"]["alias"] == "[x] Ford"
    assert edit({"op": "replace", "path": "variables.msg", "find": "Parked", "text": "Stopped"})["config"]["variables"]["msg"].startswith("Stopped.")
    assert edit({"op": "set", "path": "mode", "value": "single"})["config"]["mode"] == "single"
    assert edit({"op": "set", "path": "variables.extra", "value": "x"})["config"]["variables"]["extra"] == "x"       # new key below the top level


def test_list_indexes_reach_into_nested_actions():
    out = edit({"op": "append", "path": "actions.0.then.0.data.message", "text": " https://example.test"})
    assert out["config"]["actions"][0]["then"][0]["data"]["message"] == "{{ msg }} https://example.test"


@pytest.mark.parametrize("bad", [
    {"op": "append", "path": "variable.msg", "text": "x"},                     # the 2026-11-14 slip: variable vs variables
    {"op": "append", "path": "variables.missing", "text": "x"},
    {"op": "append", "path": "variables.n", "text": "x"},                      # not text
    {"op": "replace", "path": "variables.msg", "find": "zzz", "text": "x"},    # find occurs 0 times
    {"op": "replace", "path": "variables.msg", "find": "a", "text": "x"},      # find occurs more than once
    {"op": "set", "path": "newtop", "value": 1},                               # new top-level key
    {"op": "set", "path": "id", "value": "9"},
    {"op": "append", "path": "id", "text": "9"},
    {"op": "append", "path": "alias", "text": ""},
    {"op": "wipe", "path": "alias"},
    {"op": "set", "path": "variables"},                                        # no value
    {"op": "append", "path": "actions.7.x", "text": "x"},
])
def test_refused(bad):
    with pytest.raises(ce.EditError):
        edit(bad)


def test_edits_must_be_a_short_nonempty_list():
    for bad in (None, [], "x", [1], [{"op": "set", "path": "mode", "value": "a"}] * (ce.MAX_EDITS + 1)):
        with pytest.raises(ce.EditError):
            ce.apply_edits(AUTOMATION, bad)


def test_scripts_and_scenes_use_the_same_edits_and_their_own_paths():
    script = {"alias": "Goodnight", "sequence": [{"delay": "00:10:00"}], "mode": "single"}
    assert edit({"op": "set", "path": "sequence.0.delay", "value": "00:20:00"}, cfg=script)["config"]["sequence"][0]["delay"] == "00:20:00"
    scene = {"name": "Movie", "entities": {"light.a": {"state": "on", "brightness": 255}}}
    assert ce.config_path("script", "goodnight") == "/api/config/script/config/goodnight"
    assert ce.config_path("scene", "1700000000") == "/api/config/scene/config/1700000000"
    for bad in (("light", "x"), ("automation", "../x"), ("automation", "")):
        with pytest.raises(ce.EditError):
            ce.config_path(*bad)


def test_version_changes_with_content_not_with_key_order():
    assert ce.version(AUTOMATION) == ce.version(json.loads(json.dumps(AUTOMATION, sort_keys=True)))
    assert ce.version(AUTOMATION) != ce.version({**AUTOMATION, "mode": "single"})


def test_a_stale_version_is_refused():
    with pytest.raises(ce.EditError, match="changed since"):
        ce.plan(AUTOMATION, "stale", [{"op": "set", "path": "mode", "value": "single"}])


def test_template_pieces_are_rendered_alone_and_failures_are_sorted_into_kinds():
    def render(text):
        if "from_json" in text:
            return {"ok": False, "error": "ValueError: Template error: from_json got invalid input 'x'"}
        if "trigger" in text:
            return {"ok": False, "error": "UndefinedError: 'trigger' is undefined"}
        return {"ok": True, "text": "https://maps?q=1,2"}
    ok = ce.plan(AUTOMATION, ce.version(AUTOMATION), [{"op": "append", "path": "variables.msg", "text": " {{ 1 }}"}], render)
    assert ok["problems"] == [] and ok["renders"][0]["status"] == "ok" and "maps" in ok["renders"][0]["rendered"]
    ctx = ce.plan(AUTOMATION, ce.version(AUTOMATION), [{"op": "append", "path": "variables.msg", "text": " {{ trigger.x }}"}], render)
    assert ctx["problems"] == [] and ctx["renders"][0]["status"] == "needs_context"          # cannot be rendered alone: not a fault
    bad = ce.plan(AUTOMATION, ce.version(AUTOMATION), [{"op": "append", "path": "variables.msg", "text": " {{ from_json(gps) }}"}], render)
    assert bad["problems"] and "from_json" in bad["problems"][0]


def test_plain_text_edits_are_not_rendered():
    called = []
    out = ce.plan(AUTOMATION, ce.version(AUTOMATION), [{"op": "set", "path": "alias", "value": "New name"}], lambda t: called.append(t) or {"ok": True, "text": ""})
    assert not called and out["renders"] == []


def test_templates_inside_a_whole_section_value_are_still_collected_and_the_card_says_it_replaces_a_section():
    out = edit({"op": "set", "path": "variables", "value": {"msg": "{{ states('sensor.a') }}", "n": ["{% if x %}y{% endif %}", "plain"]}})
    assert {t["path"] for t in out["templates"]} == {"variables.msg", "variables.n.0"}
    assert "replaces a whole section" in out["changes"][0]


def test_an_ok_render_that_is_blank_is_a_warning_not_a_pass():
    out = ce.plan(AUTOMATION, ce.version(AUTOMATION), [{"op": "append", "path": "variables.msg", "text": " {{ state_attr('sensor.x', 'lat') or '' }}"}], lambda t: {"ok": True, "text": " "})
    assert out["problems"] == [] and out["renders"][0]["status"] == "empty" and "renders to nothing" in out["warnings"][0]


def test_text_that_uses_the_automations_own_variables_is_rendered_with_placeholders_and_a_trailing_dot_after_a_link_is_flagged():
    seen = []
    def render(text):
        seen.append(text)
        for name in ("decision", "current"):
            if name in text.split("%}")[-1] and "{% set " + name not in text:
                return {"ok": False, "error": "UndefinedError: '" + name + "' is undefined"}
        return {"ok": True, "text": "In PARK. Battery: 77%.\nhttps://www.google.com/maps?q=37.4,-121.9."}
    out = ce.plan(AUTOMATION, ce.version(AUTOMATION), [{"op": "append", "path": "variables.msg", "text": "{{ decision.basis }}{{ current }}"}], render)
    r = out["renders"][0]
    assert r["status"] == "ok" and r["placeholders"] == ["decision", "current"] and "37.4" in r["rendered"]
    assert out["problems"] == [] and any("punctuation" in w for w in out["warnings"])          # the 2026-11-14 'extra character at the end' bug
    clean = ce.plan(AUTOMATION, ce.version(AUTOMATION), [{"op": "append", "path": "variables.msg", "text": "{{ 1 }}"}], lambda t: {"ok": True, "text": "see https://maps?q=1,2\nBattery 5%."})
    assert clean["warnings"] == []


def test_a_name_that_stays_undefined_is_still_reported_as_needing_context():
    out = ce.plan(AUTOMATION, ce.version(AUTOMATION), [{"op": "append", "path": "variables.msg", "text": "{{ x }}"}], lambda t: {"ok": False, "error": "UndefinedError: 'x' is undefined"})
    assert out["renders"][0]["status"] == "needs_context" and out["problems"] == []


def test_value_is_accepted_for_text_operations_but_text_is_never_taken_for_set():
    out = edit({"op": "replace", "path": "variables.msg", "find": "Parked", "value": "Stopped"})
    assert out["config"]["variables"]["msg"].startswith("Stopped.")
    assert edit({"op": "append", "path": "alias", "value": "!"})["config"]["alias"] == "Ford!"
    with pytest.raises(ce.EditError):
        edit({"op": "set", "path": "mode", "text": "single"})                      # set still needs value


def test_an_unknown_function_is_reported_as_such_not_hidden_behind_a_placeholder():
    def render(text):
        if "{% set from_dict" in text:
            return {"ok": False, "error": "TypeError: 'dict' object is not callable"}          # what a placeholder would have turned it into
        return {"ok": False, "error": "UndefinedError: 'from_dict' is undefined"}
    out = ce.plan(AUTOMATION, ce.version(AUTOMATION), [{"op": "append", "path": "variables.msg", "text": "{{ from_dict(x) }}"}], render)
    assert out["renders"][0]["status"] == "error" and "not a Home Assistant template function" in out["problems"][0]
    assert "value | from_dict" in out["problems"][0] and "dict" not in out["problems"][0].replace("from_dict", "")
    var = ce.plan(AUTOMATION, ce.version(AUTOMATION), [{"op": "append", "path": "variables.msg", "text": "{{ decision.basis }}"}],
                  lambda t: {"ok": True, "text": "x"} if "{% set decision" in t else {"ok": False, "error": "UndefinedError: 'decision' is undefined"})
    assert var["renders"][0]["status"] == "ok" and var["renders"][0]["placeholders"] == ["decision"]          # a variable is still given a placeholder
