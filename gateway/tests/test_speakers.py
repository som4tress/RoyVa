"""ha_speakers behaviour with fake Home Assistant data shaped like a real home (opaque entity ids, groupable + non-groupable speakers, TVs)."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("ha_speakers", Path(__file__).resolve().parents[2] / "mcp" / "ha" / "ha_speakers.py")
hs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hs)

GROUP, PLAY, VOL = 4194304, 512, 4
def mp(eid, name, state="idle", feats=GROUP | PLAY | VOL, device_class=None):
    return {"entity_id": eid, "state": state, "attributes": {"friendly_name": name, "supported_features": feats, "device_class": device_class}}

STATES = [
    mp("media_player.living_room", "Living Room Speaker", device_class="speaker"),
    mp("media_player.unnamed_room", "Dining Room Speaker", device_class="speaker"),
    mp("media_player.unnamed_room_2", "Sitting Room Speaker", device_class="speaker"),
    mp("media_player.unnamed_room_3", "Upstairs Speaker", state="unavailable", device_class="speaker"),
    mp("media_player.office_den_speaker", "Office Den Speaker", feats=PLAY | VOL),                  # AirPlay: plays, cannot group, no device class
    mp("media_player.tv_a", "Living room television", feats=PLAY | VOL),                          # name says television
    mp("media_player.tv_b", "LG webOS TV", device_class="tv", feats=PLAY | VOL),
    {"entity_id": "tts.engine_one", "state": "unknown", "attributes": {}},
]
PLATFORMS = {"media_player.living_room": "sonos", "media_player.unnamed_room": "sonos", "media_player.unnamed_room_2": "sonos",
             "media_player.unnamed_room_3": "sonos", "media_player.office_den_speaker": "apple_tv"}


def home(states=STATES):
    posts = []
    h = hs.Home(get=lambda p: states, post=lambda p, b, **k: posts.append((p, b)) or 200, platforms=PLATFORMS)
    return h, posts


def call_data(posts, service):
    return [b for p, b in posts if p.endswith(service)]


# ------------------------------------------------------------------ discovery
def test_tvs_are_excluded_by_class_and_by_name_and_speakers_kept():
    names = [s["name"] for s in hs.speakers_from(STATES, PLATFORMS)]
    assert "Office Den Speaker" in names and "Living Room Speaker" in names
    assert "Living room television" not in names and "LG webOS TV" not in names


def test_capabilities_come_from_feature_bits():
    sp = {s["name"]: s for s in hs.speakers_from(STATES, PLATFORMS)}
    assert sp["Dining Room Speaker"]["can_group"] and not sp["Office Den Speaker"]["can_group"]
    assert sp["Office Den Speaker"]["can_play_media"]


# ------------------------------------------------------------------ target resolution
def test_resolve_by_name_partial_and_entity_id():
    sps = hs.speakers_from(STATES, PLATFORMS)
    assert [s["entity_id"] for s in hs.resolve(["Dining Room Speaker"], sps)["ok"]] == ["media_player.unnamed_room"]
    assert [s["entity_id"] for s in hs.resolve(["dining"], sps)["ok"]] == ["media_player.unnamed_room"]
    assert [s["entity_id"] for s in hs.resolve(["media_player.office_den_speaker"], sps)["ok"]] == ["media_player.office_den_speaker"]


def test_all_means_every_available_speaker_and_reports_unavailable():
    r = hs.resolve(["all"], hs.speakers_from(STATES, PLATFORMS))
    assert {s["name"] for s in r["ok"]} == {"Living Room Speaker", "Dining Room Speaker", "Sitting Room Speaker", "Office Den Speaker"}
    assert r["skipped"] == ["Upstairs Speaker (unavailable)"]


def test_ambiguous_and_unknown_targets_do_not_guess():
    sps = hs.speakers_from(STATES, PLATFORMS)
    assert "ambiguous" in hs.resolve(["room"], sps)["error"]
    err = hs.resolve(["garage"], sps)["error"]
    assert "no speaker matches 'garage'" in err and "Dining Room Speaker" in err
    assert hs.resolve(["upstairs"], sps)["error"] == "none of the requested speakers is available"


# ------------------------------------------------------------------ speak
def test_speak_sends_one_tts_call_to_all_targets_with_detected_engine():
    h, posts = home()
    out = hs.speak({"text": "Dinner is ready", "speakers": ["dining", "sitting"]}, h)
    assert out["ok"] and "Dining Room Speaker, Sitting Room Speaker" in out["did"]
    (call,) = call_data(posts, "tts/speak")
    assert call == {"entity_id": "tts.engine_one", "media_player_entity_id": ["media_player.unnamed_room", "media_player.unnamed_room_2"], "message": "Dinner is ready"}


def test_speak_truncates_long_text_and_says_so_and_sets_volume_first():
    h, posts = home()
    out = hs.speak({"text": "x" * 3000, "speakers": ["office"], "volume": 40}, h)
    assert out["truncated"] is True and "truncated" in out["did"]
    assert len(call_data(posts, "tts/speak")[0]["message"]) == hs.MAX_TEXT
    assert [p for p, _ in posts][0].endswith("volume_set") and call_data(posts, "volume_set")[0]["volume_level"] == 0.3   # asked 40: capped at the household maximum


def test_speak_without_engine_or_text_fails_clearly():
    h, _ = home([s for s in STATES if not s["entity_id"].startswith("tts.")])
    assert "no text-to-speech engine" in hs.speak({"text": "hi", "speakers": ["dining"]}, h)["error"]
    h2, _ = home()
    assert hs.speak({"text": "   ", "speakers": ["dining"]}, h2)["error"] == "nothing to say"


# ------------------------------------------------------------------ streams and grouping
def test_play_stream_validates_url():
    h, posts = home()
    assert "must start with" in hs.play_stream({"url": "file:///etc/passwd", "speakers": ["dining"]}, h)["error"]
    assert posts == []


def test_play_stream_plain_is_one_call():
    h, posts = home()
    out = hs.play_stream({"url": "https://radio.example/stream", "speakers": ["dining", "office"]}, h)
    assert out["ok"] and len([p for p in posts if not p[0].endswith("volume_set")]) == 1  # plus the safe-volume set
    assert call_data(posts, "play_media")[0]["media_content_id"] == "https://radio.example/stream"


def test_synced_play_groups_sonos_under_a_leader_and_is_honest_about_the_rest():
    h, posts = home()
    out = hs.play_stream({"url": "https://radio.example/stream", "speakers": ["all"], "synced": True}, h)
    join = call_data(posts, "/join")[0]
    assert join["entity_id"] == "media_player.living_room" and set(join["group_members"]) == {"media_player.unnamed_room", "media_player.unnamed_room_2"}
    plays = call_data(posts, "play_media")
    assert plays[0]["entity_id"] == "media_player.living_room"                                 # one play on the leader plays the whole group
    assert plays[1]["entity_id"] == ["media_player.office_den_speaker"]
    assert "NOT in sync" in out["did"] and "Upstairs Speaker (unavailable)" in out["skipped"]


def test_synced_with_one_groupable_speaker_does_not_join():
    h, posts = home()
    hs.play_stream({"url": "https://r.example/s", "speakers": ["dining", "office"], "synced": True}, h)
    assert call_data(posts, "/join") == []


def test_group_speakers_needs_two_groupable_and_reports_ungroupable():
    h, posts = home()
    bad = hs.group_speakers({"speakers": ["dining", "office"]}, h)
    assert bad["ok"] is False and "Office Den Speaker (cannot be grouped)" in bad["skipped"]
    ok = hs.group_speakers({"speakers": ["dining", "sitting", "living"], "leader": "sitting"}, h)
    assert ok["leader"] == "Sitting Room Speaker" and call_data(posts, "/join")[0]["entity_id"] == "media_player.unnamed_room_2"


# ------------------------------------------------------------------ control
@pytest.mark.parametrize("action,service", [("pause", "media_pause"), ("resume", "media_play"), ("stop", "media_stop"), ("next", "media_next_track"),
                                            ("previous", "media_previous_track"), ("volume_up", "volume_up"), ("unjoin", "unjoin")])
def test_control_maps_actions_to_services(action, service):
    h, posts = home()
    assert hs.control({"action": action, "speakers": ["dining"]}, h)["ok"]
    assert call_data(posts, service) == [{"entity_id": ["media_player.unnamed_room"]}]


def test_control_mute_and_volume_normalisation():
    h, posts = home()
    hs.control({"action": "mute", "speakers": ["dining"]}, h)
    assert call_data(posts, "volume_mute")[0]["is_volume_muted"] is True
    hs.control({"action": "set_volume", "speakers": ["dining"], "value": 50}, h)
    hs.control({"action": "set_volume", "speakers": ["dining"], "value": 0.3}, h)
    assert [c["volume_level"] for c in call_data(posts, "volume_set")] == [0.3, 0.3]
    assert "needs a value" in hs.control({"action": "set_volume", "speakers": ["dining"]}, h)["error"]
    assert "unknown action" in hs.control({"action": "explode", "speakers": ["dining"]}, h)["error"]


# ------------------------------------------------------------------ dry run: reports, never acts
def test_dry_run_makes_no_write_and_says_so(monkeypatch):
    monkeypatch.setenv("ROYVA_DRY_RUN", "1")
    h, posts = home()
    out = hs.speak({"text": "hello", "speakers": ["dining"]}, h)
    assert posts == [] and out["dry_run"] is True and out["did"].startswith("[DRY RUN, nothing happened]")
    assert h.calls and h.calls[-1][1] == "speak"                                                 # still recorded as what WOULD have happened


# ------------------------------------------------------------------ radio directory
def test_find_radio_stream_maps_fields_and_fails_over_between_hosts():
    seen = []
    def fetch(req):
        seen.append(req.full_url.split("/")[2])
        if len(seen) == 1:
            raise OSError("first host down")
        return [{"name": "Station A", "url_resolved": "https://a.example/live", "codec": "MP3", "bitrate": 128, "country": "US", "state": "CA", "votes": 9}]
    out = hs.find_radio_stream({"query": "station a", "country": "United States"}, fetch=fetch)
    assert out["stations"][0]["url"] == "https://a.example/live" and len(seen) == 2 and seen[0] != seen[1]
    assert "unreachable" in hs.find_radio_stream({"query": "x"}, fetch=lambda r: (_ for _ in ()).throw(OSError()))["error"]


def test_unknown_or_ambiguous_leader_is_an_error_not_a_silent_default():
    h, posts = home()
    out = hs.group_speakers({"speakers": ["dining", "sitting", "living"], "leader": "kitchen"}, h)
    assert out["ok"] is False and "not one of the groupable speakers" in out["error"] and posts == []
    assert "ambiguous" in hs.group_speakers({"speakers": ["dining", "sitting", "living"], "leader": "room"}, h)["error"]


# ------------------------------------------------------------------ radio: presets first, loosened search, honest empty result
def test_presets_win_over_the_public_directory_and_match_loosely():
    out = hs.find_radio_stream({"query": "Play 98.5 Kbay country"}, fetch=lambda r: pytest.fail("must not call the network"), presets={"Kbay": "https://example.com/kbay.mp3"})
    assert out["stations"][0]["url"] == "https://example.com/kbay.mp3" and out["stations"][0]["preset"] is True


def test_empty_search_is_retried_without_frequency_and_filler_words():
    queries = []
    def fetch(req):
        queries.append(req.full_url)
        return [] if len(queries) == 1 else [{"name": "Kbay", "url_resolved": "https://k.example/s", "codec": "MP3", "bitrate": 64, "country": "US", "state": "", "votes": 1}]
    out = hs.find_radio_stream({"query": "98.5 Kbay FM"}, fetch=fetch, presets={})
    assert out["stations"][0]["name"] == "Kbay" and "no exact match" in out["note"]
    assert "98.5" not in queries[1] and "name=Kbay" in queries[1]


def test_nothing_found_returns_a_hint_not_a_guess():
    out = hs.find_radio_stream({"query": "Nonexistent FM 1.1"}, fetch=lambda r: [], presets={})
    assert out["stations"] == [] and "stream URL" in out["hint"]


def test_loosen_keeps_meaningful_words():
    assert hs.loosen("98.5 Kbay Country FM") == "Kbay Country" and hs.loosen("FM 101") == ""


def test_corrupt_or_missing_presets_file_is_empty(tmp_path):
    assert hs.load_presets(tmp_path / "nope.json") == {}
    (tmp_path / "bad.json").write_text("not json")
    assert hs.load_presets(tmp_path / "bad.json") == {}


def test_rehearsal_flag_file_toggles_dry_run_without_a_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(hs, "DRY_FLAG", tmp_path / "dry_run")
    h, posts = home()
    assert hs.speak({"text": "live", "speakers": ["dining"]}, h)["dry_run"] is None and posts          # no flag: it acts
    posts.clear()
    (tmp_path / "dry_run").write_text("")
    out = hs.speak({"text": "rehearsal", "speakers": ["dining"]}, h)
    assert out["dry_run"] is True and posts == []                                                     # flag present: nothing happens
    (tmp_path / "dry_run").unlink()
    assert hs.speak({"text": "live again", "speakers": ["dining"]}, h)["dry_run"] is None and posts    # flag removed: acts again


def test_volume_is_always_set_low_before_playing_and_never_exceeds_the_ceiling():
    h, posts = home()
    hs.speak({"text": "hello", "speakers": ["dining"]}, h)                        # no volume named: safe default
    assert call_data(posts, "volume_set")[0]["volume_level"] == 0.28
    posts.clear()
    hs.play_stream({"url": "https://x.example/s", "speakers": ["dining"], "volume": 100}, h)
    assert max(c["volume_level"] for c in call_data(posts, "volume_set")) == 0.3
    out = hs.control({"action": "set_volume", "speakers": ["dining"], "value": 90}, h)
    assert "limited from 90%" in out["did"]


def test_ceiling_is_configurable(monkeypatch):
    monkeypatch.setenv("ROYVA_MAX_VOLUME", "20"); monkeypatch.setenv("ROYVA_PLAY_VOLUME", "50")
    h, posts = home()
    hs.speak({"text": "hello", "speakers": ["dining"]}, h)
    assert call_data(posts, "volume_set")[0]["volume_level"] == 0.2


def test_tts_timeout_means_speech_started_and_is_not_an_error():
    import socket
    class Slow(hs.Home):
        def __init__(self): super().__init__(get=lambda p: [], platforms={}); self._post = None
    h = hs.Home(get=lambda p: [], post=lambda p, b, **k: (_ for _ in ()).throw(TimeoutError("The read operation timed out")), platforms={})
    out = h.call("tts", "speak", {"message": "x"})
    assert out["http_status"] == 202
