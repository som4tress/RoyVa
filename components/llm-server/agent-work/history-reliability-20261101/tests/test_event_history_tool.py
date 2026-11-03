#!/usr/bin/env python3
"""Unit tests for the staged read-only entity/event history MCP tool.

No network, no credentials: read_api and ha_version are replaced with fixtures that
have the same shape as the live recorder responses.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ha_event_history", ROOT / "src/mcp/ha_event_history.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

STATES = [
    {"entity_id": "sensor.front_doorbell_last_activity", "state": "2026-11-01T15:42:57+00:00",
     "attributes": {"friendly_name": "Front Doorbell Timestamp", "category": "on_demand", "recording_status": "ready", "created_at": "2026-11-01T15:42:57+00:00"}},
    {"entity_id": "sensor.front_driveway_last_activity", "state": "2026-11-01T16:06:49+00:00",
     "attributes": {"friendly_name": "Front Driveway Timestamp", "category": "motion", "recording_status": "ready"}},
    {"entity_id": "sensor.backyard_last_activity", "state": "2026-10-30T14:48:58+00:00",
     "attributes": {"friendly_name": "Backyard Timestamp", "category": "motion", "recording_status": "ready"}},
    {"entity_id": "camera.front_doorbell_live_view", "state": "idle", "attributes": {"friendly_name": "Front Doorbell"}},
    {"entity_id": "event.front_doorbell_ding", "state": "2026-10-23T20:29:19+00:00", "attributes": {"friendly_name": "Front Doorbell Doorbell"}},
    {"entity_id": "update.orbit_bhyve_update", "state": "off", "attributes": {"friendly_name": "Orbit BHyve Update"}},
    {"entity_id": "switch.smart_outdoor_timer_zone_1_garden_smart_watering", "state": "on",
     "attributes": {"friendly_name": "Smart Outdoor Timer Zone 1 Garden smart watering"}},
    {"entity_id": "valve.smart_outdoor_timer_zone_1_garden_zone", "state": "closed",
     "attributes": {"friendly_name": "Smart Outdoor Timer Zone 1 Garden zone"}},
]

DAY = "2026-10-31"


def row(entity_id, last_changed, state="motion", **attrs):
    base = {"category": "motion", "recording_status": "ready", "created_at": state if state.endswith("Z") or "+" in state else last_changed}
    base.update(attrs)
    return {"entity_id": entity_id, "state": state, "last_changed": last_changed, "attributes": base}


HISTORY = {
    "sensor.front_doorbell_last_activity": [
        # seeded initial state at the window boundary -> excluded by default
        row("sensor.front_doorbell_last_activity", "2026-10-31T07:00:00+00:00", state="2026-10-31T04:30:53+00:00", created_at="2026-10-31T04:30:53+00:00"),
        # previous local day, outside the window
        row("sensor.front_doorbell_last_activity", "2026-10-31T06:59:00+00:00", state="2026-10-31T06:59:00+00:00", created_at="2026-10-31T06:59:00+00:00"),
        row("sensor.front_doorbell_last_activity", "2026-10-31T16:46:00+00:00", state="2026-10-31T16:46:00+00:00", created_at="2026-10-31T16:46:00+00:00"),
        # duplicate of the same recording (same created_at)
        row("sensor.front_doorbell_last_activity", "2026-10-31T16:46:02+00:00", state="2026-10-31T16:46:00+00:00", created_at="2026-10-31T16:46:00+00:00"),
        row("sensor.front_doorbell_last_activity", "2026-10-31T16:47:07+00:00", state="2026-10-31T16:47:07+00:00", created_at="2026-10-31T16:47:07+00:00"),
        row("sensor.front_doorbell_last_activity", "2026-10-31T20:00:00+00:00", state="2026-10-31T20:00:00+00:00", created_at="2026-10-31T20:00:00+00:00", category="on_demand"),
        row("sensor.front_doorbell_last_activity", "2026-10-31T21:00:00+00:00", state="2026-10-31T21:00:00+00:00", created_at="2026-10-31T21:00:00+00:00", category="ding"),
        # next local day (00:30 PDT on 2026-11-01) -> outside the requested local day
        row("sensor.front_doorbell_last_activity", "2026-11-01T07:30:00+00:00", state="2026-11-01T07:30:00+00:00", created_at="2026-11-01T07:30:00+00:00"),
    ],
    "sensor.front_driveway_last_activity": [
        row("sensor.front_driveway_last_activity", "2026-10-31T07:00:00+00:00", state="2026-10-31T04:31:16+00:00", created_at="2026-10-31T04:31:16+00:00"),
        row("sensor.front_driveway_last_activity", "2026-10-31T15:06:00+00:00", state="2026-10-31T15:06:00+00:00", created_at="2026-10-31T15:06:00+00:00"),
        row("sensor.front_driveway_last_activity", "2026-10-31T15:07:00+00:00", state="2026-10-31T15:07:00+00:00", created_at="2026-10-31T15:07:00+00:00"),
    ],
    "camera.front_doorbell_live_view": [],
}

ORIG_API = mod.read_api
ORIG_VERSION = mod.ha_version


def fake_api(path, timeout=30):
    if path == "/api/states":
        return STATES
    return []


def fake_history(entity_id, start, end):
    return HISTORY.get(entity_id, [])


SWITCH_STATES = STATES + [
    {"entity_id": "switch.test_zone", "state": "off", "attributes": {"friendly_name": "Test Zone"}},
]
SWITCH_HISTORY = {
    "switch.test_zone": [
        {"entity_id": "switch.test_zone", "state": "on", "last_changed": "2026-10-31T07:00:00+00:00", "attributes": {"created_at": "2026-10-31T07:00:00+00:00"}},
        {"entity_id": "switch.test_zone", "state": "off", "last_changed": "2026-10-31T08:00:00+00:00", "attributes": {"created_at": "2026-10-31T08:00:00+00:00"}},
        {"entity_id": "switch.test_zone", "state": "on", "last_changed": "2026-10-31T09:00:00+00:00", "attributes": {"created_at": "2026-10-31T09:00:00+00:00"}},
        {"entity_id": "switch.test_zone", "state": "unavailable", "last_changed": "2026-10-31T10:00:00+00:00", "attributes": {"created_at": "2026-10-31T10:00:00+00:00"}},
        {"entity_id": "switch.test_zone", "state": "on", "last_changed": "2026-10-31T11:00:00+00:00", "attributes": {"created_at": "2026-10-31T11:00:00+00:00"}},
        {"entity_id": "switch.test_zone", "state": "on", "last_changed": "2026-10-31T11:00:02+00:00", "attributes": {"created_at": "2026-10-31T11:00:00+00:00"}},
    ],
}


class HistoryToolTests(unittest.TestCase):
    def setUp(self):
        mod.read_api = lambda path, timeout=30: STATES if path == "/api/states" else []
        mod.ha_version = lambda: "2026.10.4"
        mod.fetch_history = fake_history

    def tearDown(self):
        mod.read_api = ORIG_API
        mod.ha_version = ORIG_VERSION

    def test_motion_filter_dedupe_and_exclusions(self):
        out = mod.collect_history({"name": "front doorbell", "date": DAY, "category": ["motion"], "recording_status": ["ready"]})
        self.assertEqual(out["kind"], "ha_entity_history")
        self.assertEqual(out["total"], 2, out)
        self.assertEqual([r["at_local"] for r in out["rows"]], ["2026-10-31T09:46:00-07:00", "2026-10-31T09:47:07-07:00"])
        self.assertEqual(out["excluded"].get("initial_state_before_window"), 2)
        self.assertEqual(out["excluded"].get("duplicate_created_at"), 1)
        self.assertEqual(out["excluded"].get("not_ding"), 1)
        self.assertEqual(out["excluded"].get("not_on_demand"), 1)
        self.assertEqual(out["excluded"].get("outside_window"), 1)
        self.assertEqual(out["evidence_class"], "observed_metadata")
        self.assertFalse(out["completeness"]["provider_complete"])
        self.assertTrue(out["read_only"])
        self.assertEqual(out["selection"]["dedupe_by"], "created_at")
        self.assertEqual(out["selection"]["unique_key"], "created_at")
        self.assertTrue(out["selection"]["initial_state_excluded"])
        self.assertEqual(out["filter_semantics"] if "filter_semantics" in out else out["selection"]["attribute_filters"]["category"], ["motion"])

    def test_counts_sum_to_total(self):
        out = mod.collect_history({"name": "front", "date": DAY, "category": ["motion"]})
        self.assertEqual(sum(c["count"] for c in out["counts_by_entity"]), out["total"])
        self.assertEqual({c["entity_id"] for c in out["counts_by_entity"]},
                         {"sensor.front_doorbell_last_activity", "sensor.front_driveway_last_activity"})
        self.assertEqual(out["total"], 4)

    def test_local_day_boundary(self):
        out = mod.collect_history({"name": "front doorbell", "date": DAY})
        stamps = [r["recorder_last_changed"] for r in out["rows"]]
        self.assertTrue(all(s.startswith("2026-10-31") for s in stamps), stamps)
        self.assertNotIn("2026-11-01T04:00:00+00:00", stamps)
        self.assertEqual(out["requested_window"]["time_zone"], "America/Los_Angeles")

    def test_include_initial_state_is_explicit(self):
        out = mod.collect_history({"name": "front doorbell", "date": DAY, "include_initial_state": True})
        self.assertTrue(any(r["recorder_last_changed"] == "2026-10-31T00:00:00-07:00" for r in out["rows"]), out["rows"])

    def test_unknown_entity_is_not_reported_as_absence(self):
        out = mod.collect_history({"name": "front gate", "date": DAY})
        self.assertEqual(out["total"], 0)
        self.assertIn("error", out)
        self.assertIn("not proof", out["limitation"])
        self.assertFalse(out["completeness"]["complete_within_source"])

    def test_dedupe_modes(self):
        by_state = mod.collect_history({"name": "front doorbell", "date": DAY, "dedupe_by": "state"})
        none = mod.collect_history({"name": "front doorbell", "date": DAY, "dedupe_by": "none"})
        created = mod.collect_history({"name": "front doorbell", "date": DAY, "dedupe_by": "created_at"})
        self.assertLessEqual(created["total"], by_state["total"])
        self.assertLessEqual(by_state["total"], none["total"])

    def test_power_cycle_filters_unavailable_duplicates_and_restore(self):
        mod.read_api = lambda path, timeout=30: SWITCH_STATES if path == "/api/states" else []
        original = mod.fetch_history
        mod.fetch_history = lambda eid, start, end: SWITCH_HISTORY.get(eid, []) if eid == "switch.test_zone" else original(eid, start, end)
        try:
            out = mod.collect_history({"name": "test zone", "date": DAY, "state": ["on"]})
        finally:
            mod.fetch_history = original
            mod.read_api = lambda path, timeout=30: STATES if path == "/api/states" else []
        self.assertEqual([r["at_local"] for r in out["rows"]],
                         ["2026-10-31T02:00:00-07:00", "2026-10-31T04:00:00-07:00"])
        self.assertEqual(out["excluded"].get("state_unavailable"), 1)
        self.assertEqual(out["excluded"].get("duplicate_created_at"), 1)
        self.assertEqual(out["excluded"].get("state_off"), 1)
        self.assertEqual(out["excluded"].get("initial_state_before_window"), 1)

    def test_dst_day_lengths_are_local_not_naive(self):
        spring, spring_start, spring_end = mod.local_day_window("2026-03-08", None)
        fall, fall_start, fall_end = mod.local_day_window("2025-11-02", None)
        self.assertEqual(spring["date"], "2026-03-08")
        # Compare absolute instants: aware subtraction with the same ZoneInfo keeps
        # wall-clock arithmetic, so use timestamps to observe the 23/25-hour day.
        self.assertEqual(spring_end.timestamp() - spring_start.timestamp(), 23 * 3600)
        self.assertEqual(fall_end.timestamp() - fall_start.timestamp(), 25 * 3600)

    def test_explicit_exclusion_is_honoured(self):
        out = mod.collect_history({"name": "front", "date": DAY, "exclude": ["driveway"]})
        ids = {c["entity_id"] for c in out["counts_by_entity"]}
        self.assertEqual(ids, {"sensor.front_doorbell_last_activity"})
        self.assertEqual(out["selection"]["excluded_terms"], ["driveway"])

    def test_rolling_window(self):
        out = mod.collect_history({"name": "front driveway", "hours": 6})
        self.assertEqual(out["requested_window"]["kind"], "rolling")
        self.assertEqual(out["requested_window"]["hours"], 6)

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            mod.collect_history({"name": "front doorbell", "date": DAY, "unknown_filter": 1})
        with self.assertRaises(ValueError):
            mod.collect_history({"name": "front doorbell", "date": DAY, "hours": 3})
        with self.assertRaises(ValueError):
            mod.collect_history({"name": "front doorbell", "limit": 5000})
        with self.assertRaises(ValueError):
            mod.collect_history({"name": "front doorbell", "date": "2999-01-01"})
        with self.assertRaises(ValueError):
            mod.collect_history({"date": DAY})
        with self.assertRaises(ValueError):
            mod.collect_history({"name": "front doorbell", "date": DAY, "include_initial_state": "yes"})

    def test_source_lookup_resolves_alias_prefix(self):
        out = mod.collect_sources({"query": "bhyve"})
        self.assertEqual(out["total_candidates"], 1, out)
        self.assertEqual(out["candidates"][0]["entity_id"], "update.orbit_bhyve_update")
        self.assertIsNone(out["no_match_note"])

    def test_source_lookup_zero_is_not_absence(self):
        out = mod.collect_sources({"query": "zzz nonexistent widget"})
        self.assertEqual(out["total_candidates"], 0)
        self.assertIn("not proof", out["no_match_note"])

    def test_source_lookup_partial_match_requires_confirmation(self):
        out = mod.collect_sources({"query": "front gate"})
        self.assertGreater(out["total_candidates"], 0)
        self.assertTrue(out["partial_only"])
        self.assertIn("confirm", out["confirmation_note"].lower())
        self.assertTrue(all("gate" in c["unmatched_tokens"] for c in out["candidates"]))

    def test_source_lookup_domain_filter(self):
        out = mod.collect_sources({"query": "smart outdoor timer", "domain": ["switch"], "limit": 5})
        self.assertTrue(out["candidates"])
        self.assertTrue(all(c["domain"] == "switch" for c in out["candidates"]))

    def test_server_is_read_only(self):
        source = (ROOT / "src/mcp/ha_event_history.py").read_text()
        for forbidden in ("/api/services", "call_service", "HassTurn", "set_state", "media_player.play"):
            self.assertNotIn(forbidden, source)
        for tool in mod.TOOLS:
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertFalse(tool["annotations"]["destructiveHint"])
        self.assertEqual({t["name"] for t in mod.TOOLS}, {"get_entity_history", "find_history_sources"})

    def test_result_is_json_serializable_and_contract_ready(self):
        out = mod.collect_history({"name": "front doorbell", "date": DAY, "category": ["motion"]})
        text = json.dumps(out)
        self.assertLess(len(text), 200000)
        for key in ("rows", "counts_by_entity", "total", "window", "requested_window", "evidence_class", "completeness", "source_versions", "limitations", "selected_sources", "excluded_sources"):
            self.assertIn(key, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
