#!/usr/bin/env python3
"""Read-only Home Assistant entity/event history MCP server.

Closes the capability gap that made historical questions fail: the existing
ha-history server only exposed recorded *person zone visits* and *current* device
states, so a camera/recording/entity-history question had no read-only tool and
models either improvised proxy counts or denied that any capability existed.

This server deliberately reports what the Home Assistant recorder observed. It
does not claim to be the Ring/provider clip list, and every response carries
evidence class, scope, exclusions and completeness so a caller cannot present
observations as provider-authoritative history.

No service calls, no writes, no arbitrary URLs. Credentials are read privately and
never echoed.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")
MAX_LIMIT = 2000
COUNTS_LIMIT = 200
DEFAULT_ATTRS = ("category", "recording_status", "answered", "friendly_name", "device_class")

TOOL_HISTORY = {
    "name": "get_entity_history",
    "description": (
        "Read recorded Home Assistant history rows for one or more entities, with optional "
        "attribute filters such as category, recording_status or state. Use for device/event/"
        "recording history questions (for example camera motion events, valve runs, switch "
        "changes) as distinct from person visit history. Returns recorder-observed rows with "
        "local timestamps, per-entity counts, explicit exclusion reasons and a provenance "
        "contract. This is HA-observed metadata, not the provider's authoritative event/clip "
        "list; events the integration never polled are not visible. Read-only."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Friendly-name substring used to resolve entities. Prefer this or entity_id."},
            "entity_id": {"type": "array", "items": {"type": "string"}, "description": "Explicit entity IDs (exact)."},
            "domain": {"type": "array", "items": {"type": "string"}, "description": "Optional domain filter when resolving by name."},
            "exclude": {"type": "array", "items": {"type": "string"}, "description": "Optional name substrings to exclude explicitly, e.g. a device the user said not to include."},
            "date": {"type": "string", "description": "Local calendar date YYYY-MM-DD (America/Los_Angeles). Omit with hours for rolling windows."},
            "hours": {"type": "integer", "minimum": 1, "maximum": 168, "description": "Rolling last N hours. Mutually exclusive with date."},
            "category": {"type": "array", "items": {"type": "string"}, "description": "Exact attribute category filter, e.g. motion, ding, on_demand."},
            "recording_status": {"type": "array", "items": {"type": "string"}, "description": "Exact recording_status filter, e.g. ready."},
            "state": {"type": "array", "items": {"type": "string"}, "description": "Exact state filter, e.g. on, off, closed, open."},
            "dedupe_by": {"type": "string", "enum": ["created_at", "state", "none"], "description": "Deduplicate identical observations (default created_at when present)."},
            "include_initial_state": {"type": "boolean", "description": "Include the seeded state row at/before the window start (default false)."},
            "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "description": "Maximum returned rows after filtering (default 500)."},
        },
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
}

TOOL_SOURCES = {
    "name": "find_history_sources",
    "description": (
        "Resolve the entities that could answer a history question, by matching words against "
        "current entity IDs, friendly names and known aliases. Use this before concluding that a "
        "device, integration or history source is absent. A zero result is explicitly reported "
        "as 'not found in current entity states', never as proof of absence. Read-only."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 2, "description": "Words from the user request, e.g. an integration, brand, device or zone name."},
            "domain": {"type": "array", "items": {"type": "string"}, "description": "Optional REST domain filter (light, switch, sensor, binary_sensor, event, valve, camera, update, ...)."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Maximum candidates to return (default 20)."},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
}

TOOLS = [TOOL_HISTORY, TOOL_SOURCES]
CONFIG_PATH = Path.home() / ".config/opencode/opencode.json"
REMOTE_PATH = Path.home() / "llm-server/ha-remote.json"


def connection():
    cfg = json.loads(CONFIG_PATH.read_text())
    ha = cfg["mcp"]["servers"]["home-assistant"]
    if ha.get("type") == "local":
        ha = json.loads(REMOTE_PATH.read_text())
    auth = ha.get("headers", {}).get("Authorization", "")
    missing = []

    def substitute(match):
        value = os.environ.get(match.group(1))
        if not value:
            missing.append(match.group(1))
        return value or ""

    auth = re.sub(r"\{env:([^}]+)\}", substitute, auth)
    if missing or not auth:
        raise ValueError("Home Assistant authentication environment is unavailable.")
    return ha, auth


def read_api(path, timeout=30):
    ha, auth = connection()
    url = ha["url"].split("/api/")[0] + path
    req = urllib.request.Request(url, headers={"Authorization": auth, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def ha_version():
    try:
        return read_api("/api/config").get("version")
    except Exception:
        return None


def local_day_window(date_text, hours):
    now = dt.datetime.now(TZ)
    if hours is not None:
        if not isinstance(hours, int) or isinstance(hours, bool) or not 1 <= hours <= 168 or date_text:
            raise ValueError("hours must be 1..168 and cannot be combined with date.")
        start = (now.astimezone(dt.timezone.utc) - dt.timedelta(hours=hours)).astimezone(TZ)
        return {"kind": "rolling", "hours": hours, "time_zone": str(TZ), "as_of": now.isoformat(timespec="seconds")}, start, now
    if date_text:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
            raise ValueError("date must be YYYY-MM-DD.")
        day = dt.date.fromisoformat(date_text)
    else:
        day = now.date()
    start = dt.datetime.combine(day, dt.time(), TZ)
    end = min(start + dt.timedelta(days=1), now) if day == now.date() else start + dt.timedelta(days=1)
    return {"kind": "local_day", "date": day.isoformat(), "time_zone": str(TZ), "from": start.isoformat(timespec="seconds"), "to": end.isoformat(timespec="seconds")}, start, end


def normalize(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").casefold()).strip()


def resolve_entities(name, entity_ids, domains, states):
    pool = []
    for row in states:
        eid = row.get("entity_id", "")
        domain = eid.split(".")[0]
        friendly = row.get("attributes", {}).get("friendly_name", eid)
        pool.append({"entity_id": eid, "name": friendly, "domain": domain})
    if entity_ids:
        wanted = set(entity_ids)
        found = [item for item in pool if item["entity_id"] in wanted]
        missing = wanted - {item["entity_id"] for item in found}
        return found, sorted(missing)
    needle = normalize(name)
    if not needle:
        raise ValueError("Provide name or entity_id.")
    tokens = [t for t in needle.split(" ") if len(t) >= 2]
    hits = []
    for item in pool:
        if domains and item["domain"] not in domains:
            continue
        hay = normalize(item["name"] + " " + item["entity_id"]).split(" ")
        if all(any(h == t or (len(t) >= 4 and h.startswith(t)) for h in hay) for t in tokens):
            hits.append(item)
    return hits, []


def fetch_history(entity_id, start, end):
    query = urllib.parse.urlencode({
        "filter_entity_id": entity_id,
        "end_time": end.isoformat(),
        "significant_changes_only": "1",
    })
    url = "/api/history/period/" + urllib.parse.quote(start.isoformat(), safe=":+-") + "?" + query
    data = read_api(url)
    if not isinstance(data, list):
        return []
    return next((group for group in data if group and group[0].get("entity_id") == entity_id), [])


SOURCE_NOUNS = {
    "timestamp", "time", "last", "activity", "event", "sensor", "binary", "motion",
    "status", "state", "live", "view", "camera", "update", "doorbell", "button",
    "recordings", "recording", "zone", "switch", "valve", "smart", "watering",
}


def device_key(name):
    """Group entity names that describe one device (view + timestamp + event entity)."""
    tokens = normalize(name).split(" ")
    while len(tokens) > 1 and tokens[-1] in SOURCE_NOUNS:
        tokens.pop()
    return " ".join(tokens).strip() or normalize(name)


def collect_history(args):
    if set(args) - {"name", "entity_id", "domain", "exclude", "date", "hours", "category", "recording_status", "state", "dedupe_by", "include_initial_state", "limit"}:
        raise ValueError("Unsupported history filter.")
    name = args.get("name", "")
    entity_ids = args.get("entity_id")
    domains = args.get("domain")
    for label, value in (("entity_id", entity_ids), ("domain", domains), ("exclude", args.get("exclude")), ("category", args.get("category")), ("recording_status", args.get("recording_status")), ("state", args.get("state"))):
        if value is not None and (not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value)):
            raise ValueError("Invalid %s filter." % label)
    if not isinstance(name, str):
        raise ValueError("name must be a string.")
    dedupe_by = args.get("dedupe_by", "created_at")
    if dedupe_by not in ("created_at", "state", "none"):
        raise ValueError("Invalid dedupe_by.")
    include_initial = args.get("include_initial_state", False)
    if not isinstance(include_initial, bool):
        raise ValueError("include_initial_state must be boolean.")
    limit = args.get("limit", 500)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError("Invalid limit.")

    window, start, end = local_day_window(args.get("date"), args.get("hours"))
    if window.get("kind") == "local_day" and dt.date.fromisoformat(window["date"]) > dt.datetime.now(TZ).date():
        raise ValueError("Cannot request future history.")

    states = read_api("/api/states")
    entities, missing = resolve_entities(name, entity_ids, domains, states)
    excluded_requests = [normalize(x) for x in (args.get("exclude") or []) if normalize(x)]
    if excluded_requests:
        entities = [item for item in entities if not any(term in normalize(item["name"] + " " + item["entity_id"]) for term in excluded_requests)]
    if not entities:
        return {
            "kind": "ha_entity_history",
            "version": 1,
            "requested_window": window,
            "error": "No entities matched the requested name/domain.",
            "missing_entity_ids": missing,
            "resolved_entities": [],
            "rows": [],
            "counts_by_entity": [],
            "total": 0,
            "excluded": {},
            "completeness": {"complete_within_source": False, "provider_complete": False},
            "limitation": "No match in current entity states is not proof that the device or integration is absent. Use find_history_sources with alternative names/aliases or inspect the device registry before concluding anything.",
            "read_only": True,
        }

    detail = {item["entity_id"]: next((row for row in states if row.get("entity_id") == item["entity_id"]), {}) for item in entities}
    rows, excluded = [], {}

    def drop(reason):
        excluded[reason] = excluded.get(reason, 0) + 1

    # Several entities can describe one device (live view, last-activity timestamp,
    # event entity). Counting each would double count, so keep one history source per
    # device and say explicitly which sources were not used.
    raw_map = {item["entity_id"]: fetch_history(item["entity_id"], start, end) for item in entities}
    wanted_attrs = bool(args.get("category") or args.get("recording_status"))

    def has_wanted_attrs(entity_id):
        return any(("category" in (row.get("attributes") or {})) if wanted_attrs else True for row in raw_map[entity_id])

    domain_rank = ["sensor", "binary_sensor", "event", "switch", "valve", "input_boolean",
                   "light", "climate", "fan", "cover", "lock", "media_player", "camera"]

    def source_score(item):
        domain = item["domain"]
        rank = domain_rank.index(domain) if domain in domain_rank else len(domain_rank)
        return (0 if has_wanted_attrs(item["entity_id"]) else 1, rank, item["entity_id"])

    groups = {}
    for item in entities:
        key = device_key(item["name"])
        groups.setdefault(key, []).append(item)

    chosen, excluded_sources = [], []
    for members in groups.values():
        members = sorted(members, key=source_score)
        chosen.append(members[0])
        for skipped in members[1:]:
            excluded_sources.append({
                "entity_id": skipped["entity_id"],
                "name": skipped["name"],
                "reason": "other_source_for_same_device",
            })
    chosen.sort(key=lambda item: item["entity_id"])

    for item in chosen:
        eid = item["entity_id"]
        raw_rows = raw_map[eid]
        entity_rows = 0
        seen = set()
        for row in raw_rows:
            attrs = row.get("attributes") or {}
            try:
                recorder_stamp = dt.datetime.fromisoformat(row["last_changed"]).astimezone(TZ)
            except Exception:
                drop("invalid_timestamp")
                continue
            # Event time is the attribute timestamp when the integration supplies one
            # (for example created_at = recording start). Recorder last_changed only
            # says when HA polled the row, so it must not place a stale event inside
            # the requested day.
            created = attrs.get("created_at") or row.get("state")
            event_stamp = recorder_stamp
            if attrs.get("created_at"):
                try:
                    event_stamp = dt.datetime.fromisoformat(str(attrs["created_at"]).replace("Z", "+00:00")).astimezone(TZ)
                except Exception:
                    event_stamp = recorder_stamp
            stamp = event_stamp
            if recorder_stamp <= start:
                # The row HA seeded at/before the window start. It carries the previous
                # event, not a new one inside the requested day.
                if not include_initial:
                    drop("initial_state_before_window")
                    continue
            elif stamp < start:
                # A stale event re-reported during the window: recorder saw the row,
                # but the event itself belongs to an earlier day.
                drop("outside_window")
                continue
            if stamp >= end:
                drop("outside_window")
                continue
            if dedupe_by != "none":
                key = created if dedupe_by == "created_at" else row.get("state")
                if key in seen:
                    drop("duplicate_" + dedupe_by)
                    continue
                seen.add(key)
            categories = args.get("category")
            if categories and attrs.get("category") not in categories:
                drop("not_" + re.sub(r"[^a-z0-9]+", "_", str(attrs.get("category") or "uncategorized").lower()))
                continue
            statuses = args.get("recording_status")
            if statuses and attrs.get("recording_status") not in statuses:
                drop("status_" + re.sub(r"[^a-z0-9]+", "_", str(attrs.get("recording_status") or "unknown").lower()))
                continue
            wanted_states = args.get("state")
            if wanted_states and str(row.get("state")) not in wanted_states:
                drop("state_" + re.sub(r"[^a-z0-9]+", "_", str(row.get("state") or "unknown").lower()))
                continue
            created_local = None
            if created:
                try:
                    created_local = dt.datetime.fromisoformat(str(created).replace("Z", "+00:00")).astimezone(TZ).isoformat(timespec="seconds")
                except Exception:
                    created_local = stamp.isoformat(timespec="seconds")
            rows.append({
                "entity_id": eid,
                "name": item["name"],
                "at_utc": stamp.astimezone(dt.timezone.utc).isoformat(timespec="seconds"),
                "at_local": created_local or stamp.isoformat(timespec="seconds"),
                "state": row.get("state"),
                "category": attrs.get("category"),
                "recording_status": attrs.get("recording_status"),
                "answered": attrs.get("answered"),
                "recorder_last_changed": recorder_stamp.isoformat(timespec="seconds"),
            })
            entity_rows += 1

    rows.sort(key=lambda r: (r["at_utc"] or "", r["entity_id"]))
    total_in_window = len(rows)
    truncated = total_in_window > limit
    rows = rows[:limit]
    per_entity = {}
    for row in rows:
        slot = per_entity.setdefault(row["entity_id"], {"count": 0, "first": None, "last": None, "name": row["name"]})
        slot["count"] += 1
        slot["first"] = slot["first"] or row["at_local"]
        slot["last"] = row["at_local"]
    counts_entities = []
    for item in chosen:
        slot = per_entity.get(item["entity_id"])
        if not slot:
            continue
        counts_entities.append({
            "entity_id": item["entity_id"],
            "name": item["name"],
            "count": slot["count"],
            "first_local": slot["first"],
            "last_local": slot["last"],
            "recorder_rows": len(raw_map[item["entity_id"]]),
            "has_event_attributes": any("category" in (row.get("attributes") or {}) for row in raw_map[item["entity_id"]]),
            "last_state": detail.get(item["entity_id"], {}).get("state"),
        })
    counts_entities.sort(key=lambda c: c["entity_id"])
    total = len(rows)
    version = ha_version()

    limitations = [
        "Counts reflect rows the Home Assistant recorder observed/polled in the requested window.",
        "Ring/provider cloud records that HA never polled are not visible; this is not the provider's authoritative clip list.",
        "A category attribute describes the last recording reported by the integration, so deduplication by created_at is required to avoid double counting.",
    ]
    if any(not c["has_event_attributes"] for c in counts_entities):
        limitations.append("At least one resolved entity exposes no event attributes; it cannot answer a trigger-type count and its rows are not event-type evidence.")
    if truncated:
        limitations.append("Response truncated at the requested limit; the total is the returned row count, not the complete in-window count.")

    return {
        "kind": "ha_entity_history",
        "version": 1,
        "source": "Home Assistant recorder history (/api/history/period)",
        "evidence_class": "observed_metadata",
        "evidence_label": "HA-observed metadata (recorder)",
        "provider_complete": False,
        "requested_window": window,
        "window": window,
        "requested_filters": {k: v for k, v in args.items() if v not in (None, "", False)},
        "selection": {
            "source": "recorder attribute/state rows",
            "name_filter": name or None,
            "explicit_entity_ids": entity_ids or None,
            "domain_filter": domains or None,
            "attribute_filters": {"category": args.get("category"), "recording_status": args.get("recording_status")},
            "state_filter": args.get("state"),
            "excluded_terms": args.get("exclude") or None,
            "dedupe_by": dedupe_by,
            "unique_key": "created_at" if dedupe_by == "created_at" else (dedupe_by if dedupe_by != "none" else "none"),
            "initial_state_excluded": not include_initial,
            "event_time_basis": "created_at when present, else recorder last_changed",
        },
        "resolved_entities": entities,
        "selected_sources": [{"entity_id": i["entity_id"], "name": i["name"]} for i in chosen],
        "excluded_sources": excluded_sources,
        "missing_entity_ids": missing,
        "rows": rows,
        "counts_by_entity": counts_entities,
        "total": total,
        "total_in_window": total_in_window,
        "returned": len(rows),
        "truncated": truncated,
        "excluded": excluded,
        "completeness": {
            "complete_within_source": not truncated,
            "provider_complete": False,
            "notes": "Recorder rows only; provider-side clips/events HA never observed are excluded and cannot be inferred from this result.",
        },
        "limitations": limitations,
        "source_versions": {"ha": version, "server": "ha-event-history/1.0.0", "schema": 1},
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "read_only": True,
    }


def collect_sources(args):
    if set(args) - {"query", "domain", "limit"}:
        raise ValueError("Unsupported source filter.")
    query = args.get("query", "")
    if not isinstance(query, str) or len(query.strip()) < 2:
        raise ValueError("Specify a distinctive query.")
    domains = args.get("domain")
    if domains is not None and (not isinstance(domains, list) or any(not isinstance(x, str) for x in domains)):
        raise ValueError("Invalid domain filter.")
    limit = args.get("limit", 20)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
        raise ValueError("Invalid limit.")

    tokens = [t for t in normalize(query).split(" ") if len(t) >= 3]
    states = read_api("/api/states")
    scored = []
    for row in states:
        eid = row.get("entity_id", "")
        domain = eid.split(".")[0]
        if domains and domain not in domains:
            continue
        attrs = row.get("attributes", {})
        friendly = attrs.get("friendly_name", eid)
        hay = normalize(friendly + " " + eid).split(" ")
        matched = [t for t in tokens if any(h == t or (len(t) >= 4 and h.startswith(t)) or (len(h) >= 4 and t.startswith(h)) for h in hay)]
        if matched:
            scored.append({
                "entity_id": eid,
                "name": friendly,
                "domain": domain,
                "state": row.get("state"),
                "matched_tokens": matched,
                "unmatched_tokens": [t for t in tokens if t not in matched],
                "has_event_attributes": "category" in attrs,
                "history_queryable": True,
                "score": len(matched) / max(1, len(tokens)),
            })
    scored.sort(key=lambda x: (-x["score"], x["domain"], x["entity_id"]))
    domains_present = {}
    for item in scored:
        domains_present[item["domain"]] = domains_present.get(item["domain"], 0) + 1
    return {
        "kind": "ha_history_sources",
        "version": 1,
        "query": query,
        "query_tokens": tokens,
        "candidates": scored[:limit],
        "total_candidates": len(scored),
        "domains": domains_present,
        "searched_entities": len(states),
        "exact_matches": sum(1 for item in scored if item["score"] >= 0.999),
        "partial_only": bool(scored) and all(item["score"] < 0.999 for item in scored),
        "no_match_note": None if scored else "No entity in the current state catalog matched these words. This is not proof that the device, integration, alias or history source is absent: check alternative names/aliases and the device registry, and use get_entity_history on a discovered entity.",
        "confirmation_note": "Only partial word matches were found; confirm the intended entity rather than assuming these are the requested device." if scored and all(item["score"] < 0.999 for item in scored) else None,
        "source_versions": {"ha": ha_version(), "server": "ha-event-history/1.0.0", "schema": 1},
        "read_only": True,
    }


def reply(message):
    ident = message.get("id")
    method = message.get("method")
    if ident is None:
        return
    if method == "initialize":
        result = {
            "protocolVersion": message.get("params", {}).get("protocolVersion", "2025-03-26"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ha-event-history", "version": "1.0.0"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        try:
            params = message.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {}) or {}
            if name == TOOL_HISTORY["name"]:
                data = collect_history(args)
            elif name == TOOL_SOURCES["name"]:
                data = collect_sources(args)
            else:
                raise ValueError("Unknown tool")
            result = {"content": [{"type": "text", "text": json.dumps(data)}], "isError": False}
        except Exception as exc:
            safe = str(exc) if isinstance(exc, ValueError) else type(exc).__name__ + " while reading HA history"
            result = {"content": [{"type": "text", "text": json.dumps({"error": safe, "read_only": True})}], "isError": True}
    elif method == "ping":
        result = {}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "Method not found"}}), flush=True)
        return
    print(json.dumps({"jsonrpc": "2.0", "id": ident, "result": result}), flush=True)


if __name__ == "__main__":
    for line in sys.stdin:
        try:
            reply(json.loads(line))
        except (ValueError, KeyError):
            continue
