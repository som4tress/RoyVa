#!/usr/bin/env python3
"""Read-only evidence probe for historical recorder metadata.

Reads HA credentials privately from ~/llm-server (never printed or stored), then
reports aggregate recorder evidence for entities that expose recording attributes.
No service calls, no writes, no downloads.
"""
import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")
HOME = Path.home()
OUT = Path(__file__).resolve().parents[2] / "evidence/live-ha-probe.json"


def credentials():
    env = {}
    env_path = HOME / "llm-server/ha.env"
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            env[key] = value.strip().strip('"').strip("'")
    remote = json.loads((HOME / "llm-server/ha-remote.json").read_text())
    return remote["url"].split("/api/")[0], env.get("HA_TOKEN")


BASE, TOKEN = credentials()


def get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + TOKEN, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def day_window(date_text):
    day = dt.date.fromisoformat(date_text)
    start = dt.datetime.combine(day, dt.time(), TZ)
    return start, start + dt.timedelta(days=1)


def history(entity_id, start, end):
    query = urllib.parse.urlencode({"filter_entity_id": entity_id, "end_time": end.isoformat(), "significant_changes_only": "1"})
    url = "/api/history/period/" + urllib.parse.quote(start.isoformat(), safe=":+-") + "?" + query
    data = get(url)
    return next((group for group in data if group and group[0].get("entity_id") == entity_id), [])


states = get("/api/states")
config = get("/api/config")
recording_entities = [s for s in states if "category" in (s.get("attributes") or {}) and "recording_status" in (s.get("attributes") or {})]

report = {
    "probe": "read-only recorder metadata evidence",
    "ha_version": config.get("version"),
    "time_zone": config.get("time_zone"),
    "entity_catalog_size": len(states),
    "recording_attribute_entities": [],
    "irrigation_alias_evidence": {},
    "capability_notes": [],
    "read_only": True,
}

date_text = os.environ.get("PROBE_DATE", "2026-10-31")
start, end = day_window(date_text)
report["window"] = {"date": date_text, "from": start.isoformat(), "to": end.isoformat(), "time_zone": str(TZ)}

for state in sorted(recording_entities, key=lambda s: s["entity_id"]):
    entity_id = state["entity_id"]
    rows = history(entity_id, start, end)
    categories, statuses = {}, {}
    in_window, initial, duplicates = [], 0, 0
    seen = set()
    for row in rows:
        attrs = row.get("attributes") or {}
        recorder_stamp = dt.datetime.fromisoformat(row["last_changed"]).astimezone(TZ)
        created = attrs.get("created_at")
        event_stamp = recorder_stamp
        if created:
            try:
                event_stamp = dt.datetime.fromisoformat(str(created).replace("Z", "+00:00")).astimezone(TZ)
            except ValueError:
                event_stamp = recorder_stamp
        if recorder_stamp <= start:
            initial += 1
            continue
        if event_stamp < start or event_stamp >= end:
            continue
        if created and created in seen:
            duplicates += 1
            continue
        seen.add(created)
        category = attrs.get("category")
        categories[category] = categories.get(category, 0) + 1
        statuses[attrs.get("recording_status")] = statuses.get(attrs.get("recording_status"), 0) + 1
        in_window.append({"at_local": event_stamp.isoformat(timespec="seconds"),
                          "category": category, "recording_status": attrs.get("recording_status")})
    motion_ready = [row for row in in_window if row["category"] == "motion" and row["recording_status"] == "ready"]
    # Comparison only: what a naive "recorder last_changed inside the day" count would
    # report. A stale event re-polled inside the window inflates this number.
    naive = []
    for row in rows:
        attrs = row.get("attributes") or {}
        stamp = dt.datetime.fromisoformat(row["last_changed"]).astimezone(TZ)
        if start < stamp < end and attrs.get("category") == "motion" and attrs.get("recording_status") == "ready":
            naive.append(attrs.get("created_at"))
    report["recording_attribute_entities"].append({
        "entity_id": entity_id,
        "friendly_name": state.get("attributes", {}).get("friendly_name"),
        "recorder_rows_in_window": len(rows),
        "initial_state_rows": initial,
        "duplicate_created_at_rows": duplicates,
        "categories": categories,
        "recording_statuses": statuses,
        "motion_ready_count": len(motion_ready),
        "naive_last_changed_motion_ready_count": len(naive),
        "naive_minus_event_time": len(naive) - len(motion_ready),
        "first_motion_local": motion_ready[0]["at_local"] if motion_ready else None,
        "last_motion_local": motion_ready[-1]["at_local"] if motion_ready else None,
    })

orbit = [s["entity_id"] for s in states if re.search(r"orbit|bhyve", s["entity_id"], re.I)]
irrigation = [s["entity_id"] for s in states if "smart_outdoor_timer" in s["entity_id"]]
report["irrigation_alias_evidence"] = {
    "orbit_or_bhyve_entities": orbit,
    "smart_outdoor_timer_entities": sorted(irrigation)[:6],
    "smart_outdoor_timer_total": len(irrigation),
    "note": "A word search for 'bhyve' finds one update entity; the integration's zones are exposed as Smart Outdoor Timer switches/valves. Absence of an exact word match is not absence of the integration.",
}
report["capability_notes"] = [
    "HA REST exposes current states and recorder history; it exposes no vendor clip/recording list endpoint.",
    "Recording category/status are attributes of the integration's last-activity timestamp sensor, so deduplication by created_at is required.",
    "Per-device counts above are HA-observed recorder metadata, not the vendor's authoritative clip list.",
]

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({k: report[k] for k in ("ha_version", "time_zone", "recording_attribute_entities", "irrigation_alias_evidence")}, indent=2)[:4000])
