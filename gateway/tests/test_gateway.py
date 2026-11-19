import asyncio
import json
import itertools
from pathlib import Path

from royva_gateway import profiles, registry
from royva_gateway.classifiers import Prediction
from royva_gateway.config import Settings
from royva_gateway.models import AskRequest
from royva_gateway.router import Router
from royva_gateway.runner import WRAP_UP
from royva_gateway.service import Gateway
from royva_gateway.sessions import SessionStore

ROOT = Path(__file__).resolve().parent.parent
REG = registry.load(ROOT / "registry")


class FakeOC:
    """Scripted stand-in for OpenCode. Normal turns finish at once; `runaway` makes the first prompt loop on tools until interrupted."""
    def __init__(self, runaway=False, mcp=None, fanout=0):
        self.sessions, self.msgs, self.calls = {}, {}, []
        self.runaway, self.fanout, self.mcp = runaway, fanout, mcp or {"home-assistant": "connected", "gmail": "connected", "ha-history": "connected", "ha-entity-history": "connected", "ha-speakers": "connected", "ha-routines": "connected", "gmail-tidy": "connected", "image-gen": "connected", "img-video": "connected"}
        self.clock = itertools.count(100, 10)
        self.n = 0

    def _add(self, sid, role, parts):
        self.n += 1
        self.msgs[sid].append({"id": f"m{self.n}", "type": role, "time": {"created": next(self.clock)}, "content": parts})

    async def mcp_status(self):
        return self.mcp

    async def create_session(self, agent, permissions):
        sid = f"ses_{len(self.sessions) + 1}"
        self.sessions[sid] = {"time": {"idle": 1, "busy": 0}}
        self.msgs[sid] = []
        self.calls.append(("create", agent, permissions))
        return sid

    async def set_permissions(self, sid, permissions):
        self.sessions.setdefault(sid, {"time": {"idle": 1, "busy": 0}})
        self.msgs.setdefault(sid, [])
        self.calls.append(("permissions", sid, permissions))

    async def prompt(self, sid, text, delivery="queue"):
        self.calls.append(("prompt", sid, text, delivery))
        if delivery == "steer":
            return
        self._add(sid, "user", [{"type": "text", "text": text}])
        user_t = self.msgs[sid][-1]["time"]["created"]
        if self.runaway and text != WRAP_UP:
            for _ in range(12):                                                # 12 separate rounds, one tool call each
                self._add(sid, "assistant", [{"type": "tool", "name": "gmail_search_messages"}])
            self.sessions[sid]["time"] = {"idle": 1, "busy": user_t}          # still running
        elif self.fanout and text != WRAP_UP:
            self._add(sid, "assistant", [{"type": "tool", "name": "GetLiveContext"} for _ in range(self.fanout)])   # ONE round, wide fan-out
            self._add(sid, "assistant", [{"type": "text", "text": "fan-out answer"}])
            self.sessions[sid]["time"] = {"idle": next(self.clock), "busy": user_t}
        else:
            self._add(sid, "assistant", [{"type": "text", "text": "wrapped answer" if text == WRAP_UP else "all good"}])
            self.sessions[sid]["time"] = {"idle": next(self.clock), "busy": user_t}

    async def messages(self, sid):
        return list(self.msgs[sid])

    async def session(self, sid):
        return self.sessions[sid]

    async def interrupt(self, sid):
        self.calls.append(("interrupt", sid))
        self.sessions[sid]["time"] = {"idle": next(self.clock), "busy": self.sessions[sid]["time"]["busy"]}


class FakeClassifier:
    def __init__(self, table):
        self.table, self.seen = table, []

    def __call__(self, text, prior, state):
        self.seen.append((text, prior))
        return Prediction(list(self.table.get(text, [])), "new")


def write_users(tmp_path, users=None):
    f = tmp_path / "users.json"
    f.write_text(json.dumps(users if users is not None else {"telegram:1": {"person": "", "scopes": ["*"], "mail": "default"}}))
    return f


def make(tmp_path, table, reg=None, users=None, **oc_kw):
    s = Settings(state_dir=tmp_path, poll_interval_s=0.0, run_timeout_s=5, users_file=write_users(tmp_path, users))
    clf = FakeClassifier(table)
    oc = FakeOC(**oc_kw)
    gw = Gateway(s, reg or REG, Router(clf, "fake"), oc, SessionStore(tmp_path / "sessions.json"))
    return gw, oc, clf


def ask(gw, text, session_id=None, reply=False):
    return asyncio.run(gw.ask(AskRequest(text=text, user="telegram:1", session_id=session_id, is_reply=reply)))


def granted(call):
    return {r["action"] for r in call[2] if r["effect"] == "allow"}


# ------------------------------------------------------------------ routing and grants
def test_new_message_creates_session_with_exact_tools(tmp_path):
    gw, oc, _ = make(tmp_path, {"lights?": ["home_state"]})
    r = ask(gw, "lights?")
    assert r.status == "done" and r.answer == "all good" and r.routing.mode == "new"
    create = next(c for c in oc.calls if c[0] == "create")
    assert create[1] == "royva"
    assert granted(create) == {"home-assistant_homeassistant__GetLiveContext", "home-assistant_llm__GetDateTime",
                               "ha-history_get_on_entities_with_context", "ha-history_get_device_status_report"}
    prompt = next(c for c in oc.calls if c[0] == "prompt")
    assert "<context>" in prompt[2] and "floors" in prompt[2] and prompt[2].endswith("lights?")


def test_never_grant_tools_are_denied(tmp_path):
    gw, oc, _ = make(tmp_path, {"x": ["home_state"]})
    ask(gw, "x")
    create = next(c for c in oc.calls if c[0] == "create")
    denied = {r["action"] for r in create[2] if r["effect"] == "deny"}
    assert {"skill", "shell", "edit", "write", "read"} <= denied
    assert not ({"skill", "shell"} & granted(create))


def test_reply_continues_session_without_regranting_or_repeating_context(tmp_path):
    gw, oc, clf = make(tmp_path, {"lights?": ["home_state"], "and downstairs?": ["home_state"]})
    r1 = ask(gw, "lights?")
    r2 = ask(gw, "and downstairs?", session_id=r1.session_id, reply=True)
    assert r2.routing.mode == "continuation" and r2.session_id == r1.session_id
    assert [c for c in oc.calls if c[0] in ("create", "permissions")] == [c for c in oc.calls if c[0] == "create"]
    assert clf.seen[1][1] == {"text": "lights?", "intents": ["home_state"]}        # prior turn given as context
    second_prompt = [c for c in oc.calls if c[0] == "prompt"][1][2]
    assert "floors" not in second_prompt                                            # context sent only once per session


def test_new_intent_in_existing_session_widens_grants(tmp_path):
    gw, oc, _ = make(tmp_path, {"lights?": ["home_state"], "forecast?": ["web_lookup"]})
    r1 = ask(gw, "lights?")
    r2 = ask(gw, "forecast?", session_id=r1.session_id, reply=True)
    assert r2.routing.mode == "new"
    perm = next(c for c in oc.calls if c[0] == "permissions")
    assert {"websearch", "webfetch", "home-assistant_homeassistant__GetLiveContext"} <= granted(perm)   # union, only grows
    assert set(gw.store.get(r1.session_id).tools) >= {"web.search", "ha.get_live_context"}


# ------------------------------------------------------------------ deterministic paths
def test_busy_session_is_steered_not_classified(tmp_path):
    gw, oc, clf = make(tmp_path, {"lights?": ["home_state"]})
    r1 = ask(gw, "lights?")
    st = gw.store.get(r1.session_id)
    st.busy = True
    gw.store.put(st)
    r2 = ask(gw, "actually only the kitchen", session_id=r1.session_id, reply=True)
    assert r2.status == "busy_steered" and r2.routing.mode == "steer"
    assert ("prompt", r1.session_id, "actually only the kitchen", "steer") in oc.calls
    assert len(clf.seen) == 1                                                        # classifier not called for the steer


def test_planned_intent_falls_back_to_general_mode_not_a_refusal(tmp_path):
    gw, oc, _ = make(tmp_path, {"what's on my calendar?": ["calendar"]})
    r = ask(gw, "what's on my calendar?")
    assert r.status == "done" and "can't do that yet" not in r.answer
    create = next(c for c in oc.calls if c[0] == "create")
    assert "home-assistant_homeassistant__GetLiveContext" in granted(create)               # reads from every skill are open
    prompt = next(c for c in oc.calls if c[0] == "prompt")[2]
    assert "No specific skill matched" in prompt and "not supported yet" not in prompt
    rows = [json.loads(x) for x in (tmp_path / "traces.jsonl").read_text().splitlines()]
    assert rows[-1]["chosen"] == ["general"] and "calendar.list_events" in rows[-1]["missing"]      # the gap is still logged as demand


def test_unrouted_message_gets_general_mode_with_writes_behind_approval(tmp_path):
    gw, oc, _ = make(tmp_path, {})
    r = ask(gw, "tell me a joke")
    assert r.routing.mode == "fallback" and r.status == "done"
    create = next(c for c in oc.calls if c[0] == "create")
    asks = {x["action"] for x in create[2] if x["effect"] == "ask"}
    assert "home-assistant_intent__HassTurnOff" in asks and "home-assistant_intent__HassTurnOff" not in granted(create)
    assert not any("send" in a for a in granted(create) | asks)                                 # sending mail is never opened by a session, general mode included


def test_general_mode_never_downgrades_a_skills_own_grant():
    from royva_gateway import profiles, general
    ctrl = REG.intents["home_control"]
    g = general.build(REG, [i for i in REG.active()])
    out = profiles.grants(REG, [g, ctrl])
    assert out["ha.turn_on"] == "allow" and profiles.grants(REG, [g])["ha.turn_on"] == "ask"


def test_session_created_outside_gateway_is_adopted(tmp_path):
    gw, oc, _ = make(tmp_path, {"lights?": ["home_state"]})
    r = ask(gw, "lights?", session_id="ses_foreign", reply=True)
    assert r.session_id == "ses_foreign"
    assert ("permissions", "ses_foreign") == next((c[0], c[1]) for c in oc.calls if c[0] == "permissions")


# ------------------------------------------------------------------ loop guard (bug B6)
def test_runaway_tool_loop_is_cut_off_and_wrapped_up(tmp_path):
    gw, oc, _ = make(tmp_path, {"oldest unread?": ["mail_read"]}, runaway=True)
    r = ask(gw, "oldest unread?")
    kinds = [c[0] for c in oc.calls]
    assert "interrupt" in kinds
    assert any(c[0] == "prompt" and c[2] == WRAP_UP for c in oc.calls)
    assert r.answer == "wrapped answer"
    trace = (tmp_path / "traces.jsonl").read_text()
    assert '"outcome": "wrapped"' in trace


# ------------------------------------------------------------------ readiness (bug B3) and persistence
def test_ready_only_when_all_mcp_connected(tmp_path):
    gw, _, _ = make(tmp_path, {}, mcp={"home-assistant": "connected", "gmail": "connecting", "ha-history": "connected", "ha-entity-history": "connected", "ha-speakers": "connected", "ha-routines": "connected", "gmail-tidy": "connected", "image-gen": "connected", "img-video": "connected"})
    assert asyncio.run(gw.wait_ready(timeout=0.2, poll=0.05)) is False
    gw2, _, _ = make(tmp_path, {})
    assert asyncio.run(gw2.wait_ready(timeout=1, poll=0.05)) is True


def test_session_state_survives_restart(tmp_path):
    gw, _, _ = make(tmp_path, {"lights?": ["home_state"]})
    r = ask(gw, "lights?")
    reloaded = SessionStore(tmp_path / "sessions.json").get(r.session_id)
    assert reloaded.last_intents == ["home_state"] and reloaded.turns == 1 and "home_map" in reloaded.contexts_sent


# ------------------------------------------------------------------ generated home context
def test_home_map_groups_areas_by_floor_and_warns_floors_are_not_areas():
    from royva_gateway import home_context
    snap = {"floors": {"up": {"floor_id": "up", "name": "Upstairs", "level": 1}, "down": {"floor_id": "down", "name": "Downstairs", "level": 0}},
            "areas": {"a": {"area_id": "a", "name": "Master Bedroom", "floor_id": "up"}, "b": {"area_id": "b", "name": "Temple", "floor_id": "up"},
                      "c": {"area_id": "c", "name": "Kitchen", "floor_id": "down"}, "d": {"area_id": "d", "name": "Garage", "floor_id": None}}}
    text = home_context.home_map(snap)
    assert text.index("Downstairs: Kitchen") < text.index("Upstairs: Master Bedroom, Temple")      # ordered by floor level
    assert "Other areas (no floor): Garage" in text and "NOT areas" in text


def test_home_location_is_coarse_and_has_units():
    from royva_gateway import home_context
    text = home_context.home_location({"latitude": 37.4431874, "longitude": -121.9019521, "time_zone": "America/Los_Angeles",
                                       "unit_system": {"temperature": "°F", "length": "mi", "wind_speed": "mph"}})
    assert "names a different city" in text and "37.4N, 121.9W" in text and "37.4431874" not in text and "America/Los_Angeles" in text and "°F" in text


def test_dynamic_context_overrides_static(tmp_path):
    gw, oc, _ = make(tmp_path, {"lights?": ["home_state"]})
    gw.s.dynamic_context["home_map"] = "Home layout: Upstairs: Temple."
    ask(gw, "lights?")
    assert "Upstairs: Temple" in next(c for c in oc.calls if c[0] == "prompt")[2]


def test_wide_parallel_fanout_in_one_round_is_not_cut_off(tmp_path):
    """Regression: 'and downstairs?' needs one tool call per area (8) in a single round; the guard once killed it."""
    gw, oc, _ = make(tmp_path, {"floor?": ["home_state"]}, fanout=8)
    r = ask(gw, "floor?")
    assert r.answer == "fan-out answer"
    assert not any(c[0] == "interrupt" for c in oc.calls)
    assert '"outcome": "ok"' in (tmp_path / "traces.jsonl").read_text()


def test_round_counting_ignores_text_and_counts_rounds_not_calls():
    from royva_gateway.runner import count_rounds, count_tool_calls
    rows = [{"type": "assistant", "content": [{"type": "tool"}] * 8}, {"type": "assistant", "content": [{"type": "text", "text": "x"}]},
            {"type": "assistant", "content": [{"type": "tool"}]}]
    assert count_rounds(rows) == 2 and count_tool_calls(rows) == 9


# ------------------------------------------------------------------ bridge path: new_session + route (the bridge runs the turn itself)
def test_new_session_has_base_agent_and_no_tools(tmp_path):
    gw, oc, _ = make(tmp_path, {})
    sid = asyncio.run(gw.new_session())
    create = next(c for c in oc.calls if c[0] == "create")
    assert create[1] == "royva" and granted(create) == set()
    assert gw.store.get(sid).tools == []


def test_route_grants_tools_to_bridge_created_session_and_does_not_run(tmp_path):
    gw, oc, _ = make(tmp_path, {"lights?": ["home_state"]})
    sid = asyncio.run(gw.new_session())
    out = asyncio.run(gw.route_for_bridge(AskRequest(text="lights?", user="telegram:1", session_id=sid, is_reply=False)))
    assert out["kind"] == "run" and out["session_id"] == sid and out["intents"] == ["home_state"] and out["cap"] == 6
    assert out["prompt"].endswith("lights?") and "<context>" in out["prompt"]
    perm = next(c for c in oc.calls if c[0] == "permissions")
    assert "home-assistant_homeassistant__GetLiveContext" in granted(perm)
    assert not [c for c in oc.calls if c[0] == "prompt"]                      # the gateway never ran the model on this path
    st = gw.store.get(sid)
    assert st.last_intents == ["home_state"] and st.turns == 1 and "home_map" in st.contexts_sent


def test_route_followup_inherits_prior_and_skips_context(tmp_path):
    gw, oc, clf = make(tmp_path, {"lights?": ["home_state"], "and downstairs?": ["home_state"]})
    sid = asyncio.run(gw.new_session())
    asyncio.run(gw.route_for_bridge(AskRequest(text="lights?", user="t", session_id=sid)))
    out = asyncio.run(gw.route_for_bridge(AskRequest(text="and downstairs?", user="t", session_id=sid, is_reply=True)))
    assert out["mode"] == "continuation" and "floors" not in out["prompt"]        # home map already sent in this session
    assert clf.seen[-1][1] == {"text": "lights?", "intents": ["home_state"]}


def test_route_planned_intent_runs_in_general_mode(tmp_path):
    gw, oc, _ = make(tmp_path, {"calendar?": ["calendar"]})
    sid = asyncio.run(gw.new_session())
    out = asyncio.run(gw.route_for_bridge(AskRequest(text="calendar?", user="t", session_id=sid)))
    assert out["kind"] == "run" and out["can_act"] and "No specific skill matched" in out["prompt"]


# ------------------------------------------------------------------ travel-aware location (per-message, city-level)
def test_away_text_uses_city_only_and_skips_when_home():
    from royva_gateway import home_context
    away = {"at_home": False, "zone": "not_home", "city": "Boston", "region": "MA"}
    text = home_context.away_text(away)
    assert "Boston, MA" in text and "unless they name another place" in text
    assert home_context.away_text({"at_home": True, "zone": "home", "city": "Milpitas", "region": "CA"}) is None
    assert home_context.away_text({"at_home": False, "zone": "unknown", "city": None, "region": None}) is None
    assert "at Hands on Learning" in home_context.away_text({"at_home": False, "zone": "Hands on Learning", "city": "Milpitas", "region": "CA"})


def test_person_place_never_reads_the_street_address_state():
    from royva_gateway import home_context
    data = {"/api/states/person.somdutta": {"state": "not_home"},
            "/api/states/sensor.somdutta_iphone_geocoded_location": {"state": "830 SECRET St\nCity", "attributes": {"Locality": "Boston", "Administrative Area": "MA"}}}
    info = home_context.person_place("somdutta", fetch=lambda path: data.get(path))
    assert info == {"at_home": False, "zone": "not_home", "city": "Boston", "region": "MA"}
    assert "SECRET" not in str(info)


def test_current_location_is_added_every_turn_when_away_and_not_cached(tmp_path):
    gw, oc, _ = make(tmp_path, {"forecast?": ["web_lookup"], "and tomorrow?": ["web_lookup"]})
    async def fake(user):
        return "The user is currently away from home, in Boston, MA."
    gw.current_location_text = fake
    r1 = ask(gw, "forecast?")
    r2 = ask(gw, "and tomorrow?", session_id=r1.session_id, reply=True)
    prompts = [c[2] for c in oc.calls if c[0] == "prompt"]
    assert "Boston, MA" in prompts[0] and "Boston, MA" in prompts[1]               # sent on BOTH turns
    assert "Home location" in prompts[0] and "Home location" not in prompts[1]      # static context only once
    assert "current_location" not in gw.store.get(r1.session_id).contexts_sent


def test_at_home_adds_no_location_line(tmp_path):
    gw, oc, _ = make(tmp_path, {"forecast?": ["web_lookup"]})
    async def fake(user):
        return None
    gw.current_location_text = fake
    ask(gw, "forecast?")
    assert "currently away" not in next(c for c in oc.calls if c[0] == "prompt")[2]


def test_intent_style_hint_is_added_to_the_prompt(tmp_path):
    gw, oc, _ = make(tmp_path, {"status?": ["home_state"]})
    ask(gw, "status?")
    prompt = next(c for c in oc.calls if c[0] == "prompt")[2]
    assert "Answer style:" in prompt and "diagnostic" in prompt             # the intent's style rule reaches the model


def test_vehicle_distance_intent_has_history_tools_and_date(tmp_path):
    gw, oc, _ = make(tmp_path, {"how far did the car go?": ["home_history"]})
    ask(gw, "how far did the car go?")
    perms = granted(next(c for c in oc.calls if c[0] == "create"))
    assert {"ha-entity-history_find_entities", "ha-entity-history_get_numeric_change", "home-assistant_llm__GetDateTime"} <= perms


# ------------------------------------------------------------------ guard: no household- or prompt-specific values in code
def test_code_contains_no_household_specific_terms():
    """Everything specific to this household/home must come from Home Assistant or deployment config, never from code."""
    import re
    forbidden = re.compile(r"shobha|shivangsh|mustang|milpitas|santa clara|goodnight|kbay|printer|(?<!/home/)somdutta", re.I)
    files = list((ROOT / "royva_gateway").glob("*.py")) + [ROOT.parent / "mcp" / "ha" / n for n in ("ha_entity_history.py", "ha_routines.py", "ha_speakers.py")] + [ROOT.parent / "mcp" / "mail" / "gmail_tidy.py"]
    hits = [(f.name, i + 1, line.strip()[:80]) for f in files for i, line in enumerate(f.read_text().splitlines()) if forbidden.search(line)]
    assert not hits, hits


def test_household_text_is_generated_from_person_entities():
    from royva_gateway import home_context
    text = home_context.household(["pat", "alex", "sam"], "alex")
    assert "The user asking is alex" in text and "alex, pat, sam" in text and "'All of us' means every one" in text
    assert home_context.household([], "") == "The user is a member of the household. Their email is Gmail."
    assert home_context.build_from({"floors": {}, "areas": {}}, {"latitude": 1.0, "longitude": 2.0}, "", ["pat"], "pat")["user_profile"].startswith("The user asking is pat")


def test_no_default_person_means_no_location_lookup(tmp_path):
    gw, _, _ = make(tmp_path, {})
    assert asyncio.run(gw.current_location_text("telegram:1")) is None          # Settings.default_person is empty unless deployment config sets it


# ------------------------------------------------------------------ safety model: allow / ask
def _reg_with_active_write_intent(tmp_path, policy):
    import json, shutil
    root = tmp_path / "reg"
    shutil.copytree(ROOT / "registry", root)
    p = root / "intents" / "home_control.json"
    d = json.loads(p.read_text())
    d["status"] = "active"
    d["profile"]["write_policy"] = policy
    p.write_text(json.dumps(d))
    return registry.load(root)


def test_confirm_policy_write_tools_are_granted_as_ask(tmp_path):
    reg = _reg_with_active_write_intent(tmp_path, "confirm")
    gw, oc, _ = make(tmp_path, {"turn it off": ["home_control"]}, reg=reg)
    ask(gw, "turn it off")
    rules = {r["action"]: r["effect"] for r in next(c for c in oc.calls if c[0] == "create")[2]}
    assert rules["home-assistant_intent__HassTurnOff"] == "ask"                     # human approval via the bridge's /approve flow
    assert rules["home-assistant_homeassistant__GetLiveContext"] == "allow"          # reads stay frictionless


def test_auto_policy_write_tools_are_allowed(tmp_path):
    reg = _reg_with_active_write_intent(tmp_path, "auto")
    gw, oc, _ = make(tmp_path, {"turn it off": ["home_control"]}, reg=reg)
    ask(gw, "turn it off")
    rules = {r["action"]: r["effect"] for r in next(c for c in oc.calls if c[0] == "create")[2]}
    assert rules["home-assistant_intent__HassTurnOff"] == "allow"


def test_strictest_policy_wins_and_read_only_refuses_write_tools():
    from royva_gateway import profiles
    from royva_gateway.models import Intent
    def mk(i, policy, tools):
        return Intent.model_validate(dict(id=i, status="active", description="d" * 12, examples=[f"e{n}{i}" for n in range(5)], negatives=["n1", "n2"],
                                          profile=dict(tools=tools, write_policy=policy)))
    auto = mk("a_auto", "auto", ["ha.turn_off", "ha.get_live_context"])
    confirm = mk("b_confirm", "confirm", ["ha.turn_off"])
    assert profiles.grants(REG, [auto])["ha.turn_off"] == "allow"
    assert profiles.grants(REG, [auto, confirm])["ha.turn_off"] == "ask"             # the stricter intent in the same session wins
    ro = mk("c_ro", "read_only", ["ha.turn_off", "ha.get_live_context"])              # bypasses registry validation on purpose: runtime defence
    g = profiles.grants(REG, [ro])
    assert "ha.turn_off" not in g and g["ha.get_live_context"] == "allow"


def test_unavailable_tools_are_never_granted():
    from royva_gateway import profiles
    from royva_gateway.models import Intent
    i = Intent.model_validate(dict(id="x_planned", status="active", description="d" * 12, examples=[f"e{n}" for n in range(5)], negatives=["n1", "n2"],
                                   profile=dict(tools=["calendar.list_events", "ha.get_live_context"], write_policy="read_only")))
    assert set(profiles.grants(REG, [i])) == {"ha.get_live_context"}


def test_widening_is_detected_by_effect_change_not_only_tool_set(tmp_path):
    """A session first granted a tool as 'allow' and later needing it as 'ask' must be re-permissioned."""
    reg = _reg_with_active_write_intent(tmp_path, "confirm")
    gw, oc, _ = make(tmp_path, {"lights?": ["home_state"], "turn it off": ["home_control"]}, reg=reg)
    r1 = ask(gw, "lights?")
    r2 = ask(gw, "turn it off", session_id=r1.session_id, reply=True)
    perm = next(c for c in oc.calls if c[0] == "permissions")
    assert {r["action"]: r["effect"] for r in perm[2]}["home-assistant_intent__HassTurnOff"] == "ask"
    assert gw.store.get(r2.session_id).grants["ha.turn_off"] == "ask"


# ------------------------------------------------------------------ privacy scopes: email only for users granted it
def ask_as(gw, text, user, session_id=None, reply=False):
    return asyncio.run(gw.ask(AskRequest(text=text, user=user, session_id=session_id, is_reply=reply)))


def test_owner_may_use_email_but_an_unlisted_user_is_refused_and_nothing_runs(tmp_path):
    gw, oc, _ = make(tmp_path, {"find invoices": ["mail_read"]}, users={"telegram:1": {"person": "", "scopes": ["*"], "mail": "default"}, "_policy": {"silent_scopes": []}})
    assert ask_as(gw, "find invoices", "telegram:1").status == "done"
    n_calls = len(oc.calls)
    r = ask_as(gw, "find invoices", "telegram:2")                                  # not in users.json -> no private scopes
    assert "gmail access is limited to the account owner" in r.answer
    assert len(oc.calls) == n_calls                                                  # no session, no grants, no model run for the refused user
    assert '"outcome": "forbidden"' in (tmp_path / "traces.jsonl").read_text()


def test_scope_list_grants_exactly_that_scope(tmp_path):
    users = {"telegram:3": {"person": "", "scopes": ["gmail"]}, "telegram:4": {"person": "", "scopes": ["location"]}}
    gw, oc, _ = make(tmp_path, {"find invoices": ["mail_read"]}, users=users)
    assert ask_as(gw, "find invoices", "telegram:3").status == "done"
    assert "limited to the account owner" in ask_as(gw, "find invoices", "telegram:4").answer


def test_mixed_request_for_an_unprivileged_user_keeps_the_allowed_part_and_drops_email_tools(tmp_path):
    gw, oc, _ = make(tmp_path, {"lights and mail": ["home_state", "mail_read"]})
    r = ask_as(gw, "lights and mail", "telegram:2")
    assert r.status == "done" and r.routing.intents == ["home_state", "mail_read"]
    create = next(c for c in oc.calls if c[0] == "create")
    assert not any(a.startswith("gmail_") for a in granted(create)) and "home-assistant_homeassistant__GetLiveContext" in granted(create)
    assert "gmail access is limited to the account owner" in next(c for c in oc.calls if c[0] == "prompt")[2]


def test_a_second_user_in_the_same_session_never_inherits_the_owners_email_tools(tmp_path):
    gw, oc, _ = make(tmp_path, {"find invoices": ["mail_read"], "lights?": ["home_state"]})
    r1 = ask_as(gw, "find invoices", "telegram:1")
    ask_as(gw, "lights?", "telegram:2", session_id=r1.session_id, reply=True)
    perm = [c for c in oc.calls if c[0] == "permissions"][-1]
    assert not any(a.startswith("gmail_") for a in granted(perm))


def test_missing_or_corrupt_users_file_means_no_private_scopes(tmp_path):
    gw, oc, _ = make(tmp_path, {"find invoices": ["mail_read"]})
    gw.s.users_file.write_text("{ not json")
    assert "limited to the account owner" in ask_as(gw, "find invoices", "telegram:1").answer
    gw.s.users_file.unlink()
    assert "limited to the account owner" in ask_as(gw, "find invoices", "telegram:1").answer


def test_users_file_changes_apply_without_restart(tmp_path):
    gw, _, _ = make(tmp_path, {"find invoices": ["mail_read"]}, users={})
    assert "limited to the account owner" in ask_as(gw, "find invoices", "telegram:7").answer
    import os, time
    write_users(tmp_path, {"telegram:7": {"person": "", "scopes": ["gmail"]}})
    os.utime(gw.s.users_file, (time.time() + 5, time.time() + 5))
    assert ask_as(gw, "find invoices", "telegram:7").status == "done"


# ------------------------------------------------------------------ multi-intent requests are told to finish every part
def test_combined_intents_get_an_instruction_to_deliver_not_just_reply(tmp_path):
    gw, oc, _ = make(tmp_path, {"read me the news": ["web_lookup", "media_playback"], "forecast?": ["web_lookup"]})
    ask(gw, "read me the news")
    prompt = next(c for c in oc.calls if c[0] == "prompt")[2]
    assert "combines several capabilities (web lookup, media playback)" in prompt and "instead of only replying in text" in prompt
    ask(gw, "forecast?")
    assert "combines several capabilities" not in [c for c in oc.calls if c[0] == "prompt"][1][2]


def test_write_intents_tell_the_model_to_admit_a_dry_run():
    for iid in ("media_playback", "routine_trigger"):
        assert "DRY RUN" in REG.intents[iid].profile.style


def test_house_actions_are_open_to_every_allowed_user_only_email_is_partitioned(tmp_path):
    """Owner decision: anyone on the bot may run routines and drive speakers; the only private scope is email."""
    gw, oc, _ = make(tmp_path, {"goodnight": ["routine_trigger"], "play music": ["media_playback"], "find invoices": ["mail_read"]}, users=SILENT)
    assert ask_as(gw, "goodnight", "telegram:2").status == "done"
    assert ask_as(gw, "play music", "telegram:2").status == "done"
    assert ask_as(gw, "find invoices", "telegram:2").answer == ""                          # email stays silent for everyone but the owner
    assert REG.intents["media_playback"].profile.scope == "" and REG.intents["routine_trigger"].profile.scope == "" and REG.intents["mail_read"].profile.scope == "gmail"


# ------------------------------------------------------------------ silent refusals (no reply at all) for configured scopes
SILENT = {"telegram:1": {"person": "", "scopes": ["*"], "mail": "default"}, "_policy": {"silent_scopes": ["gmail"]}}


def test_email_refusal_is_completely_silent_when_configured(tmp_path):
    gw, oc, _ = make(tmp_path, {"find invoices": ["mail_read"]}, users=SILENT)
    r = ask_as(gw, "find invoices", "telegram:2")
    assert r.answer == "" and not oc.calls                                                # no reply text, no session, no tools
    assert '"outcome": "forbidden_silent"' in (tmp_path / "traces.jsonl").read_text()
    assert ask_as(gw, "find invoices", "telegram:1").status == "done" and ask_as(gw, "find invoices", "telegram:1").answer == "all good"


def test_bridge_route_reports_silent_so_nothing_is_sent(tmp_path):
    gw, _, _ = make(tmp_path, {"find invoices": ["mail_read"]}, users=SILENT)
    out = asyncio.run(gw.route_for_bridge(AskRequest(text="find invoices", user="telegram:2")))
    assert out["kind"] == "silent" and out["answer"] == ""


def test_a_scope_not_listed_as_silent_still_gets_a_polite_refusal(tmp_path):
    gw, _, _ = make(tmp_path, {"find invoices": ["mail_read"]}, users={"telegram:1": {"person": "", "scopes": ["*"], "mail": "default"}, "_policy": {"silent_scopes": []}})
    assert "gmail access is limited to the account owner" in ask_as(gw, "find invoices", "telegram:2").answer


def test_mixed_request_for_a_silent_scope_answers_the_allowed_part_without_mentioning_email(tmp_path):
    gw, oc, _ = make(tmp_path, {"lights and mail": ["home_state", "mail_read"]}, users=SILENT)
    r = ask_as(gw, "lights and mail", "telegram:2")
    assert r.status == "done"
    prompt = next(c for c in oc.calls if c[0] == "prompt")[2]
    assert "email" not in prompt.lower() and not any(a.startswith("gmail_") for a in granted(next(c for c in oc.calls if c[0] == "create")))


def test_now_text_gives_the_model_a_real_date_and_year():
    from datetime import datetime, timezone
    out = profiles.now_text(datetime(2026, 11, 8, 21, 5, tzinfo=timezone.utc))
    assert "2026" in out and "Sunday" in out and "never an older one" in out


def test_time_intents_get_the_clock_every_turn_and_it_is_not_cached():
    reg = registry.load(Path(__file__).resolve().parents[1] / "registry")
    for iid in ("web_lookup", "home_history", "mail_read"):
        assert "current_time" in reg.intents[iid].profile.context
    assert "current_time" in profiles.PER_TURN_PROVIDERS


def test_user_allowed_email_but_without_a_connected_mailbox_is_told_so(tmp_path):
    users = {"telegram:1": {"person": "", "scopes": ["*"], "mail": "default"}, "telegram:5": {"person": "", "scopes": ["gmail"]}}
    gw, oc, _ = make(tmp_path, {"find invoices": ["mail_read"]}, users=users)
    r = ask_as(gw, "find invoices", "telegram:5")
    assert "isn't connected" in r.answer and not oc.calls                  # no session, no tools, no improvised reply
    assert ask_as(gw, "find invoices", "telegram:1").answer == "all good"      # the owner (default mailbox) is unaffected


# ------------------------------------------------------------------ follow-ups inherit what the previous turn acted on
def _tool(tool, **inp):
    return {"type": "tool", "name": tool, "state": {"status": "completed", "input": inp}}


def test_follow_up_gets_previous_scope_but_new_conversation_does_not(tmp_path):
    from royva_gateway.scope import last_turn_calls
    gw, oc, _ = make(tmp_path, {"lights on": ["home_state"], "turn off everything but one": ["home_state"], "weather": ["home_state"]})
    r1 = ask(gw, "lights on")
    oc._add(r1.session_id, "assistant", [_tool("home-assistant_light__HassLightSet", name="Island Dimmer", brightness=100),
                                         _tool("home-assistant_light__HassLightSet", name="NT50W", brightness=100),
                                         {"type": "tool", "name": "failed_one", "state": {"status": "error", "input": {"name": "X"}}}])
    ask(gw, "turn off everything but one", session_id=r1.session_id, reply=True)
    follow = [c for c in oc.calls if c[0] == "prompt"][1][2]
    assert "HassLightSet(name=Island Dimmer, brightness=100)" in follow and "NT50W" in follow and "failed_one" not in follow
    assert "not the whole home" in follow
    ask(gw, "weather")                                                              # a new standalone message: new session, nothing inherited
    assert "HassLightSet" not in [c for c in oc.calls if c[0] == "prompt"][2][2]
    assert last_turn_calls([]) == []


def test_scope_lookup_failure_never_breaks_the_turn(tmp_path):
    gw, oc, _ = make(tmp_path, {"a": ["home_state"], "b": ["home_state"]})
    r1 = ask(gw, "a")
    async def boom(sid): raise RuntimeError("down")
    oc.messages = boom
    r2 = ask(gw, "b", session_id=r1.session_id, reply=True)
    assert r2.status == "done" or r2.answer


def test_protected_devices_line_only_for_home_writes():
    from royva_gateway import profiles
    assert "Protected devices: Box A" in profiles.style_hint([], ("Box A",), True)
    assert profiles.style_hint([], ("Box A",), False) == "" and profiles.style_hint([], (), True) == ""


def test_general_mode_respects_scopes(tmp_path):
    gw, oc, _ = make(tmp_path, {}, users={"telegram:1": {"person": "", "scopes": [], "mail": ""}})
    ask(gw, "tell me a joke")
    create = next(c for c in oc.calls if c[0] == "create")
    assert not any("gmail" in x["action"] and x["effect"] != "deny" for x in create[2])       # no gmail scope: no mail tools in general mode
    assert any(x["action"] == "home-assistant_homeassistant__GetLiveContext" for x in create[2])


def test_ha_api_tools_are_owner_only_and_always_ask(tmp_path):
    gw, oc, _ = make(tmp_path, {"turn on the kitchen light": ["home_control"]})
    ask(gw, "turn on the kitchen light")
    create = next(c for c in oc.calls if c[0] == "create")
    rules = {x["action"]: x["effect"] for x in create[2]}
    assert rules["ha-api_ha_read"] == "allow" and rules["ha-api_ha_write"] == "ask"                 # home_control is auto-policy; this tool still asks
    assert rules["home-assistant_intent__HassTurnOn"] == "allow"
    (tmp_path / "b").mkdir()
    gw2, oc2, _ = make(tmp_path / "b", {"turn on the kitchen light": ["home_control"]}, users={"telegram:1": {"person": "", "scopes": ["home"], "mail": ""}})
    ask(gw2, "turn on the kitchen light")
    c2 = next(c for c in oc2.calls if c[0] == "create")
    assert not any(x["action"].startswith("ha-api_") and x["effect"] != "deny" for x in c2[2])      # no owner scope: no API door


def test_machine_door_is_general_mode_owner_only_and_run_approved_asks(tmp_path):
    gw, oc, _ = make(tmp_path, {})
    ask(gw, "how much memory is free?")
    create = next(c for c in oc.calls if c[0] == "create")
    rules = {x["action"]: x["effect"] for x in create[2]}
    assert rules["machine_run"] == "allow" and rules["machine_remote_run"] == "allow"
    assert rules["machine_run_approved"] == "ask" and rules["machine_remote_run_approved"] == "ask"
    (tmp_path / "b").mkdir()
    gw2, oc2, _ = make(tmp_path / "b", {}, users={"telegram:1": {"person": "", "scopes": ["home"], "mail": ""}})
    ask(gw2, "how much memory is free?")
    c2 = next(c for c in oc2.calls if c[0] == "create")
    assert not any(x["action"].startswith("machine_") and x["effect"] != "deny" for x in c2[2])        # an invited member never gets a shell


def test_machine_tools_are_not_in_routed_skills(tmp_path):
    gw, oc, _ = make(tmp_path, {"lights?": ["home_state"]})
    ask(gw, "lights?")
    create = next(c for c in oc.calls if c[0] == "create")
    assert not any(x["action"].startswith("machine_") and x["effect"] != "deny" for x in create[2])


def test_resolve_ids_matches_each_id_to_its_own_registry_and_reports_missing():
    from royva_gateway import home_context as hc
    snap = {"devices": {"dev1": {"id": "dev1", "name": "Tuya HAP", "name_by_user": "HAP-603WF-Bedroom", "area_id": "master_bedroom"}},
            "areas": {"master_bedroom": {"area_id": "master_bedroom", "name": "Master Bedroom"}}, "floors": {},
            "entities": {"switch.a": {"entity_id": "switch.a", "name": None, "original_name": None, "device_id": "dev1"}}}
    out = hc.resolve_ids({"device_id": ["dev1", "nope"], "area_id": ["master_bedroom"], "entity_id": ["switch.a", "light.yaml"]}, snap,
                         [{"entity_id": "switch.a", "attributes": {"friendly_name": "A Switch"}}, {"entity_id": "light.yaml", "attributes": {"friendly_name": "Yaml Light"}}])
    assert out["device_id"] == {"dev1": {"name": "HAP-603WF-Bedroom"}}                    # the UI name, and the unknown id is simply absent
    assert out["area_id"] == {"master_bedroom": {"name": "Master Bedroom"}}              # the device in the area does not rename the area
    assert out["entity_id"] == {"switch.a": {"name": "A Switch"}, "light.yaml": {"name": "Yaml Light"}}


def test_prompts_tell_the_model_to_call_approval_tools_directly_not_ask_in_text():
    from royva_gateway import general
    assert "call them directly" in general.STYLE and "never ask for confirmation in plain text" in general.STYLE
    assert "ha_write" in REG.intents["home_control"].profile.style and "never ask in text first" in REG.intents["home_control"].profile.style



# ------------------------------------------------------------------ restricted identities (programs calling /v1/ask): only the intents listed for them, whatever the router says
AGENT_USERS = {"telegram:1": {"person": "", "scopes": ["*"], "mail": "default"}, "agent:x": {"person": "", "scopes": [], "mail": "", "only_intents": ["web_lookup"]}}


def test_a_restricted_identity_is_rerouted_to_its_only_intent_even_if_the_router_picks_another(tmp_path):
    gw, oc, _ = make(tmp_path, {"top 10 headlines": ["home_control"]}, users=AGENT_USERS)
    r = ask_as(gw, "top 10 headlines", "agent:x")
    assert r.status == "done" and r.routing.intents == ["web_lookup"]
    create = next(c for c in oc.calls if c[0] == "create")
    assert not any("light" in a or "turn_on" in a for a in granted(create))               # nothing from the intent the router chose reached the session
    assert '"outcome": "restricted_reroute"' in (tmp_path / "traces.jsonl").read_text()


def test_a_restricted_identity_that_already_routes_correctly_is_left_alone(tmp_path):
    gw, oc, _ = make(tmp_path, {"weather?": ["web_lookup"]}, users=AGENT_USERS)
    r = ask_as(gw, "weather?", "agent:x")
    assert r.routing.intents == ["web_lookup"] and '"outcome": "restricted_reroute"' not in (tmp_path / "traces.jsonl").read_text()


def test_restricted_identity_with_several_allowed_intents_keeps_only_those_and_fails_closed_when_none_match(tmp_path):
    users = {"agent:y": {"person": "", "scopes": [], "mail": "", "only_intents": ["web_lookup", "home_state"]}}
    gw, oc, _ = make(tmp_path, {"mixed": ["home_state", "home_control"], "nothing": ["home_control"]}, users=users)
    assert ask_as(gw, "mixed", "agent:y").routing.intents == ["home_state"]
    n = len(oc.calls)
    r = ask_as(gw, "nothing", "agent:y")
    assert "isn't something this account is allowed" in r.answer and len(oc.calls) == n          # no session, no model run


def test_unrestricted_users_are_unaffected(tmp_path):
    gw, oc, _ = make(tmp_path, {"lights": ["home_state"]}, users=AGENT_USERS)
    assert ask_as(gw, "lights", "telegram:1").routing.intents == ["home_state"]


def test_video_request_never_stays_on_picture_intents():
    from royva_gateway.router import video_not_pictures as f
    assert f("make a video of today's headlines", ["image_set"]) == ["image_generate"]
    assert f("a sarcastic video of 10 stories", ["image_generate"]) == ["image_generate"]
    assert f("Make 10 pictures, one per headline", ["image_set"]) == ["image_set"]
    assert f("Play a video on the TV", ["media_playback"]) == ["media_playback"]
    assert f("make a video and turn off the lights", ["image_generate", "home_control"]) == ["image_generate", "home_control"]
    assert f("hello", []) == []


def test_video_turn_loses_chat_search_only_for_pure_video_requests():
    from royva_gateway.router import is_video_turn as f
    assert f("make a satirical video of the top 10 headlines", ["image_generate"])
    assert f("a video of cats", ["image_set"])
    assert not f("search the news and make a video", ["web_lookup", "image_generate"])   # mixed turn keeps its search
    assert not f("what are the top headlines today?", ["web_lookup"])
    assert not f("make a meme about the news", ["image_generate"])                      # a picture keeps its news search
    assert not f("hello", [])


def test_video_turn_grants_exclude_web_search(tmp_path):
    gw, oc, _ = make(tmp_path, {"make a video of cats": ["image_generate"], "make a meme about cats": ["image_generate"]})
    v = ask_as(gw, "make a video of cats", "telegram:1")
    m = ask_as(gw, "make a meme about cats", "telegram:2")
    assert "web.search" not in v.routing.profile_tools and "image.video" in v.routing.profile_tools
    assert "web.search" in m.routing.profile_tools
