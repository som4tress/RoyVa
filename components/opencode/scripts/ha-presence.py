#!/usr/bin/env python3
"""Presence report for Home Assistant persons.

Usage: ha-presence.py [name ...]     (default: shobha)
Nicknames: pecky -> shobha

Prints, per person: in-zone? (zone name + age), the freshest tracker fix,
the iCloud3 fix, and straight-line distance from the home zone centre.
Reads HA_TOKEN from the environment. Never prints the token.
"""
import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timezone

BASE = "https://som4tress.duckdns.org:8123/api/states/"
ALIASES = {"pecky": "shobha", "som": "somdutta", "shivi": "shivangsh"}
HOME_RADIUS_M = 100.0


def get(entity):
    req = urllib.request.Request(
        BASE + entity,
        headers={"Authorization": f"Bearer {os.environ['HA_TOKEN']}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except Exception as e:  # 404 = entity does not exist
        return {"_error": str(e)}


def haversine_mi(lat1, lon1, lat2, lon2):
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def age(ts):
    if not ts:
        return "?"
    then = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    mins = (datetime.now(timezone.utc) - then).total_seconds() / 60
    if mins < 1:
        return "just now"
    if mins < 90:
        return f"{mins:.0f} min ago"
    return f"{mins / 60:.1f} h ago"


def discover(person):
    """All device_trackers belonging to a person, by entity-id prefix."""
    req = urllib.request.Request(
        BASE.rstrip("/"), headers={"Authorization": f"Bearer {os.environ['HA_TOKEN']}"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        states = json.load(r)
    out = []
    for s in states:
        eid = s["entity_id"]
        if not eid.startswith("device_tracker."):
            continue
        slug = eid.split(".", 1)[1]
        if slug == person or slug.startswith(person + "_") or slug.startswith(person + "s_"):
            out.append(eid)
    return out


def fix(entity):
    s = get(entity)
    if "_error" in s or "latitude" not in s.get("attributes", {}):
        return None
    a = s["attributes"]
    if not a.get("latitude") and not a.get("longitude"):
        return None  # 0,0 = no GPS fix, not a real position
    return {
        "entity": entity,
        "state": s["state"],
        "lat": a["latitude"],
        "lon": a["longitude"],
        "acc": a.get("gps_accuracy"),
        "age": age(s.get("last_updated")),
        "updated": s.get("last_updated"),
    }


def report(person, home):
    print(f"=== {person} ===")
    p = get(f"person.{person}")
    if "_error" not in p:
        src = (p.get("attributes") or {}).get("source")
        print(f"person.{person}: state={p['state']} source={src} age={age(p.get('last_updated'))}")

    trackers = [t for t in (fix(e) for e in discover(person)) if t]
    best = None
    for t in trackers:
        t["mi"] = haversine_mi(home["lat"], home["lon"], t["lat"], t["lon"])
        print(
            f"  {t['entity']}: state={t['state']!r} {t['mi']:.2f} mi from home"
            f" (+-{t['acc']}m) age={t['age']}"
        )
        if best is None or t["updated"] > best["updated"]:
            best = t

    for e in discover(person):
        icloud = get(e)
        if "_error" in icloud or "attributes" not in icloud:
            continue
        if "zone" not in icloud["attributes"]:
            continue
        z = icloud["attributes"].get("zone")
        print(f"  iCloud3 {e}: zone={z or 'not in a zone'} located={icloud['attributes'].get('located')}"
              f" next_update={icloud['attributes'].get('next_update')}")

    if best:
        edge = best["mi"] * 1609.34 - HOME_RADIUS_M
        inside = best["state"] not in ("not_home", "unknown", "unavailable") and edge <= 0
        verdict = f"IN a zone ({best['state']})" if inside else "AWAY (outside home zone)"
        print(f"  -> {verdict}; {best['mi']:.2f} mi ({best['mi'] * 1609.34:.0f} m) from home,"
              f" {max(edge, 0) / 1609.34:.2f} mi outside the zone edge")
        if len(trackers) > 1:
            spread = max(t["mi"] for t in trackers) - min(t["mi"] for t in trackers)
            if spread > 0.3:
                print(f"  !! trackers disagree by {spread:.2f} mi - trust the freshest ({best['entity']})")
    print()


def main():
    names = [ALIASES.get(a.lower(), a.lower()) for a in sys.argv[1:]] or ["shobha"]
    h = get("zone.home")
    home = {"lat": h["attributes"]["latitude"], "lon": h["attributes"]["longitude"]}
    print(f"home zone centre: {home['lat']:.5f},{home['lon']:.5f} radius={h['attributes'].get('radius')}m\n")
    for n in names:
        report(n, home)


if __name__ == "__main__":
    main()
