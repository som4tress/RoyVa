"""ha_routines safety properties, tested with fakes only (no real Home Assistant call is ever made)."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("ha_routines", Path(__file__).resolve().parents[2] / "mcp" / "ha" / "ha_routines.py")
hr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hr)

STATES = [
    {"entity_id": "automation.good_night", "attributes": {"friendly_name": "Good Night", "last_triggered": "2026-11-07T04:00:00+00:00"}},
    {"entity_id": "automation.good_morning", "attributes": {"friendly_name": "Good Morning"}},
    {"entity_id": "automation.home_away", "attributes": {"friendly_name": "Home Away"}},
    {"entity_id": "script.movie_time", "attributes": {"friendly_name": "Movie Time"}},
    {"entity_id": "scene.dinner", "attributes": {"friendly_name": "Dinner"}},
    {"entity_id": "light.kitchen", "attributes": {"friendly_name": "Kitchen"}},          # not a routine: must never be listed or run
    {"entity_id": "automation.night_light_a", "attributes": {"friendly_name": "Night Light A"}},
    {"entity_id": "automation.night_light_b", "attributes": {"friendly_name": "Night Light B"}},
]


def test_names_match_ignoring_case_spaces_and_punctuation():
    assert hr.plan_run("goodnight", STATES, {hr.norm("Good Night")})["entity_id"] == "automation.good_night"
    assert hr.plan_run("GOOD-night!", STATES, {hr.norm("automation.good_night")})["ok"] is True


def test_empty_allowlist_runs_nothing():
    plan = hr.plan_run("good night", STATES, set())
    assert "error" in plan and "not on the allowed list" in plan["error"] and not plan.get("ok")


def test_only_allowed_routines_run_not_their_neighbours():
    allow = {hr.norm("Good Night")}
    assert hr.plan_run("good night", STATES, allow)["ok"] is True
    assert "not on the allowed list" in hr.plan_run("good morning", STATES, allow)["error"]


def test_non_routine_entities_are_never_listed_or_runnable():
    names = [r["entity_id"] for r in hr.routines(STATES)]
    assert "light.kitchen" not in names
    assert "no routine matches" in hr.plan_run("kitchen", STATES, {hr.norm("kitchen"), hr.norm("light.kitchen")})["error"]


def test_ambiguous_names_do_not_guess():
    plan = hr.plan_run("night light", STATES, {hr.norm("night light a"), hr.norm("night light b")})
    assert plan["error"] == "ambiguous" and set(plan["candidates"]) == {"Night Light A", "Night Light B"}


@pytest.mark.parametrize("name,service", [("Good Night", "automation.trigger"), ("Movie Time", "script.turn_on"), ("Dinner", "scene.turn_on")])
def test_each_routine_type_uses_its_own_service(name, service):
    assert hr.plan_run(name, STATES, {hr.norm(name)})["service"] == service


def test_run_routine_calls_only_the_planned_service_with_only_that_entity():
    calls = []
    out = hr.run_routine({"name": "Good Night"}, get=lambda p: STATES, post=lambda p, b: calls.append((p, b)) or 200, allow={hr.norm("Good Night")})
    assert out["ok"] and calls == [("/api/services/automation/trigger", {"entity_id": "automation.good_night"})]


def test_refused_runs_never_reach_the_network():
    calls = []
    out = hr.run_routine({"name": "Good Morning"}, get=lambda p: STATES, post=lambda p, b: calls.append(p) or 200, allow={hr.norm("Good Night")})
    assert "error" in out and calls == []


def test_missing_or_corrupt_allowlist_means_nothing_is_allowed(tmp_path):
    assert hr.load_allowlist(tmp_path / "nope.json") == set()
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    assert hr.load_allowlist(bad) == set()
    good = tmp_path / "ok.json"
    good.write_text(json.dumps(["Good Night", "script.movie_time"]))
    assert hr.load_allowlist(good) == {"goodnight", "scriptmovietime"}


def test_list_marks_which_routines_are_allowed():
    out = hr.list_routines({}, get=lambda p: STATES, allow={hr.norm("Good Night")})
    flags = {r["name"]: r["allowed_to_run"] for r in out["routines"]}
    assert flags["Good Night"] is True and flags["Good Morning"] is False and "Kitchen" not in flags


def test_rehearsal_flag_file_stops_routines_from_running(tmp_path, monkeypatch):
    monkeypatch.setattr(hr, "DRY_FLAG", tmp_path / "dry_run")
    (tmp_path / "dry_run").write_text("")
    calls = []
    out = hr.run_routine({"name": "Good Night"}, get=lambda p: STATES, post=lambda p, b: calls.append(p) or 200, allow={hr.norm("Good Night")})
    assert calls == [] and out["dry_run"] is True and "[DRY RUN" in out["did"]
