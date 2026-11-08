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
        self.runaway, self.fanout, self.mcp = runaway, fanout, mcp or {"home-assistant": "connected", "gmail": "connected", "ha-history": "connected", "ha-entity-history": "connected", "ha-speakers": "connected", "ha-routines": "connected", "gmail-tidy": "connected"}
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


def test_planned_intent_gets_honest_reply_and_no_session(tmp_path):
    gw, oc, _ = make(tmp_path, {"what's on my calendar?": ["calendar"]})
    r = ask(gw, "what's on my calendar?")
    assert "can't do that yet" in r.answer and "calendar.list_events" in r.answer
    assert r.session_id is None and not [c for c in oc.calls if c[0] == "create"]


def test_unrouted_message_gets_session_with_no_tools(tmp_path):
    gw, oc, _ = make(tmp_path, {})
    r = ask(gw, "tell me a joke")
    assert r.routing.mode == "fallback" and r.status == "done"
    create = next(c for c in oc.calls if c[0] == "create")
    assert granted(create) == set()


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
    gw, _, _ = make(tmp_path, {}, mcp={"home-assistant": "connected", "gmail": "connecting", "ha-history": "connected", "ha-entity-history": "connected", "ha-speakers": "connected", "ha-routines": "connected", "gmail-tidy": "connected"})
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


def test_route_planned_intent_returns_direct_answer(tmp_path):
    gw, oc, _ = make(tmp_path, {"calendar?": ["calendar"]})
    sid = asyncio.run(gw.new_session())
    out = asyncio.run(gw.route_for_bridge(AskRequest(text="calendar?", user="t", session_id=sid)))
    assert out["kind"] == "answer" and "can't do that yet" in out["answer"]
    assert gw.store.get(sid).turns == 0                                       # nothing committed for an unsupported request


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
