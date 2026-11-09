"""A name lookup must find ANY Home Assistant entity (sensors, binary sensors, diagnostics), not just controllable ones."""
import importlib.util
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mcp" / "ha"))
SPEC = importlib.util.spec_from_file_location("ha_status_report", Path(__file__).resolve().parents[2] / "mcp" / "ha" / "ha_status_report.py")
sr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sr)

STATES = [
    {"entity_id": "binary_sensor.oven_cooktop_status", "state": "off", "attributes": {"friendly_name": "Stovetop SATV173380P Cooktop Status"}},
    {"entity_id": "switch.upper_oven_sabbath", "state": "off", "attributes": {"friendly_name": "Sabbath Mode"}},
    {"entity_id": "light.den", "state": "on", "attributes": {"friendly_name": "Den Light"}},
    {"entity_id": "sensor.attic_temp", "state": "61", "attributes": {"friendly_name": "Attic temperature"}},
    {"entity_id": "sensor.range_fault", "state": "ok", "attributes": {"friendly_name": "Fault code"}},
]
REG = {"entities": {"binary_sensor.oven_cooktop_status": {"entity_category": "diagnostic", "device_id": "d1"},
                    "sensor.range_fault": {"device_id": "d1"}, "light.den": {"area_id": "den"}},
       "devices": {"d1": {"name": "Gas Range", "area_id": "kitchen"}}, "areas": {"kitchen": {"name": "Kitchen"}, "den": {"name": "Den"}}, "floors": {}}


def run(args, monkeypatch, registry=REG):
    monkeypatch.setitem(sys.modules, "ha_registry", types.SimpleNamespace(snapshot=lambda: registry))
    return sr.collect(args, lambda path: STATES)


def devices(out):
    return [r[0] for r in out["rows"]]


def test_name_search_finds_a_diagnostic_binary_sensor_with_no_domain_given(monkeypatch):
    out = run({"name": "cooktop"}, monkeypatch)
    assert devices(out) == ["Stovetop SATV173380P Cooktop Status"]


def test_name_matches_device_and_area_words_not_only_the_friendly_name(monkeypatch):
    assert "Fault code" in devices(run({"name": "gas range"}, monkeypatch))          # device name
    assert "Den Light" in devices(run({"name": "den"}, monkeypatch))                   # area / friendly


def test_words_in_any_order_all_must_match(monkeypatch):
    assert devices(run({"name": "status cooktop"}, monkeypatch)) == ["Stovetop SATV173380P Cooktop Status"]
    assert devices(run({"name": "cooktop banana"}, monkeypatch)) == []


def test_no_name_still_means_controllable_domains_only(monkeypatch):
    out = run({}, monkeypatch)
    assert "Attic temperature" not in devices(out) and "Den Light" in devices(out)


def test_zero_hits_returns_closest_names_not_a_dead_end(monkeypatch):
    out = run({"name": "cooktap status"}, monkeypatch)
    assert out["rows"] == [] and out["suggestions"] and "Cooktop" in out["suggestions"][0]
    assert "do not tell the user the device does not exist" in out["note"]


def test_name_search_still_works_if_the_registry_is_unavailable(monkeypatch):
    def boom():
        raise RuntimeError("registry down")
    monkeypatch.setitem(sys.modules, "ha_registry", types.SimpleNamespace(snapshot=boom))
    out = sr.collect({"name": "cooktop"}, lambda path: STATES)
    assert devices(out) == ["Stovetop SATV173380P Cooktop Status"]


def test_lights_question_includes_switches_for_the_caller_to_judge(monkeypatch):
    states = STATES + [{"entity_id": "switch.porch_plug", "state": "on", "attributes": {"friendly_name": "Porch Lamp"}}]
    monkeypatch.setitem(sys.modules, "ha_registry", types.SimpleNamespace(snapshot=lambda: REG))
    out = sr.collect({"domains": ["light"]}, lambda path: states)
    assert {r[0]: r[1] for r in out["rows"]}["Porch Lamp"] == "switch"        # no name vocabulary: switches are returned, tagged, with a note
    assert "wired as switches" in out["note"]
    assert "wired as switches" not in sr.collect({"domains": ["sensor"]}, lambda path: states).get("note", "")
