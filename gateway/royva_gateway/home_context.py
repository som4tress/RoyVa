"""Generate the 'home_map' and 'home_location' context from Home Assistant's own registries (floors -> areas, home config).
`build_from` is pure (testable); `load` talks to HA through the vendored read-only helper in mcp/ha/."""
from __future__ import annotations

import sys
from pathlib import Path

HA_HELPER_DIR = Path(__file__).resolve().parent.parent.parent / "mcp" / "ha"


def home_map(snapshot: dict) -> str:
    floors, areas = snapshot["floors"], snapshot["areas"]
    by_floor: dict = {}
    for a in areas.values():
        by_floor.setdefault(a.get("floor_id"), []).append(a["name"])
    lines = []
    for fid, f in sorted(floors.items(), key=lambda kv: (kv[1].get("level") is None, kv[1].get("level"), kv[1]["name"])):
        names = sorted(by_floor.get(fid, []))
        if names:
            lines.append(f"{f['name']}: " + ", ".join(names))
    other = sorted(by_floor.get(None, []))
    if other:
        lines.append("Other areas (no floor): " + ", ".join(other))
    floor_names = ", ".join(f["name"] for f in floors.values())
    return ("Home layout, floors then their areas. " + " | ".join(lines) + ". "
            f"Floors ({floor_names}) are NOT areas: for a question about a floor, check every area listed on that floor "
            "(or fetch the whole home and filter to those areas) and report grouped by area. Use the exact area names above.")


def home_location(config: dict, place: str = "") -> str:
    lat, lon = config.get("latitude"), config.get("longitude")
    coarse = f"{round(lat, 1)}N, {abs(round(lon, 1))}{'W' if lon < 0 else 'E'}" if lat is not None and lon is not None else "unknown"
    units = (config.get("unit_system") or {})
    where = place or f"coordinates about {coarse}"
    return (f"Home location: {where}; time zone {config.get('time_zone', 'unknown')}; "
            f"units {units.get('temperature', '')} / {units.get('length', '')} / {units.get('wind_speed', '')}. "
            "Use this for weather and local questions when the user does not name a place. If the user names a different city or place (for example while travelling), use that place instead.")


def household(persons: list[str], user_person: str = "") -> str:
    """Who lives here, from Home Assistant person entities (object ids are what the history tools expect)."""
    names = sorted(persons)
    who = f"The user asking is {user_person}. " if user_person else ""
    return (who + "Household members tracked by Home Assistant: " + ", ".join(names) + ". 'All of us' means every one of them "
            "(query each person). Their email is Gmail.") if names else "The user is a member of the household. Their email is Gmail."


def speakers(names: list[str]) -> str:
    names = sorted({n for n in names if n})[:30]
    return ("Speakers and media players are Home Assistant media_player entities; use these exact names: " + ", ".join(names) + ".") if names else ""


def build_from(snapshot: dict, config: dict, place: str = "", persons: list[str] | None = None, user_person: str = "",
               players: list[str] | None = None) -> dict[str, str]:
    out = {"home_map": home_map(snapshot), "home_location": home_location(config, place)}
    if players:
        out["speakers"] = speakers(players)
    if persons:
        out["user_profile"] = household(persons, user_person)
    return out


def load(place: str = "", user_person: str = "") -> dict[str, str]:
    """Read HA registries + config. Needs HA_TOKEN in the environment (scripts/env.sh sources it)."""
    sys.path.insert(0, str(HA_HELPER_DIR))
    import ha_registry, ha_ws                                  # noqa: E401  (vendored helpers)
    snap = ha_registry.snapshot()
    ws_url, token = ha_registry._connection()
    res = ha_ws.call(ws_url, token, [{"id": 1, "type": "get_config"}, {"id": 2, "type": "get_states"}])
    persons = [x["entity_id"].split(".", 1)[1] for x in res[2] if x["entity_id"].startswith("person.")]
    players = [x["attributes"].get("friendly_name") or x["entity_id"] for x in res[2] if x["entity_id"].startswith("media_player.")]
    return build_from(snap, res[1], place, persons, user_person, players)


# ---------------------------------------------------------------- where the user is right now (per-message context; privacy: city-level only)
import json as _json
import urllib.request as _urlreq


def _rest_get(path: str):
    """GET a Home Assistant REST path using the same private connection as the registry helper. Returns None on 404/unavailable."""
    sys.path.insert(0, str(HA_HELPER_DIR))
    import ha_registry                                              # noqa: E401
    ws_url, token = ha_registry._connection()
    base = ws_url.replace("wss://", "https://").replace("ws://", "http://").replace("/api/websocket", "")
    req = _urlreq.Request(base + path, headers={"Authorization": f"Bearer {token}"})
    try:
        with _urlreq.urlopen(req, timeout=8) as r:
            return _json.load(r)
    except Exception:                                               # noqa: BLE001
        return None


def person_place(person: str, fetch=_rest_get, sensor: str = "") -> dict:
    """{'at_home': bool, 'zone': state, 'city', 'region'} for a household person. Only city/region attributes of the geocoded sensor are used;
    its state is a full street address and is never read into the result."""
    p = fetch(f"/api/states/person.{person}") or {}
    state = p.get("state", "unknown")
    geo = fetch(f"/api/states/{sensor or f'sensor.{person}_iphone_geocoded_location'}") or {}
    a = geo.get("attributes", {})
    return {"at_home": state == "home", "zone": state, "city": a.get("Locality"), "region": a.get("Administrative Area")}


def away_text(info: dict):
    """Context line for a turn, or None when the user is home (the static home location applies) or unknown."""
    if info.get("at_home") or info.get("zone") in ("unknown", "unavailable", None):
        return None
    where = ", ".join(x for x in (info.get("city"), info.get("region")) if x)
    zone = info.get("zone")
    at = f" (at {zone})" if zone and zone != "not_home" else ""
    if not where:
        return None
    return (f"The user is currently away from home, in {where}{at}. For 'here', weather and nearby questions use this location "
            "unless they name another place.")
