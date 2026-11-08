"""Failure-injection tests: the gateway must fail closed, contain errors, and never leave state corrupt."""
import asyncio
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from royva_gateway import registry, service as service_mod
from royva_gateway.classifiers import LLMClassifier, Prediction
from royva_gateway.config import Settings
from royva_gateway.models import AskRequest, SessionState
from royva_gateway.opencode_client import OpenCodeClient, OpenCodeError
from royva_gateway.router import Entry, Router, RouterUnavailable
from royva_gateway.service import Gateway, MSG_BACKEND_DOWN, MSG_ROUTER_DOWN
from royva_gateway.sessions import SessionStore

from test_gateway import FakeClassifier, FakeOC, REG, ROOT, ask, make, write_users


def run(coro):
    return asyncio.run(coro)


def req(text, sid=None, reply=False):
    return AskRequest(text=text, user="telegram:1", session_id=sid, is_reply=reply)


# ------------------------------------------------------------------ router chain: failover, circuit breaker, fail closed
class Flaky:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, 0

    def __call__(self, text, prior, state):
        self.calls += 1
        if self.error:
            raise self.error
        return Prediction(list(self.result), "new")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_chain_falls_over_to_next_classifier():
    primary, secondary = Flaky(error=ConnectionError("down")), Flaky(["home_state"])
    r = Router(chain=[Entry("big", primary), Entry("small", secondary)])
    d = run(r.decide(req("lights?"), None))
    assert d.intents == ["home_state"] and d.classifier == "small"


def test_circuit_breaker_skips_a_failing_classifier_then_recovers():
    clock = Clock()
    primary, secondary = Flaky(error=ConnectionError("down")), Flaky(["home_state"])
    r = Router(chain=[Entry("big", primary), Entry("small", secondary)], clock=clock, breaker_threshold=2, breaker_cooldown_s=30)
    run(r.decide(req("a"), None)); run(r.decide(req("b"), None))           # two failures open the circuit
    assert primary.calls == 2
    run(r.decide(req("c"), None))
    assert primary.calls == 2                                                # skipped while open
    assert r.health()[0]["circuit"] == "open"
    clock.t = 31
    assert r.health()[0]["circuit"] == "half-open"                           # cooldown over, not yet proven healthy
    primary.error, primary.result = None, ["web_lookup"]                     # the service came back
    d = run(r.decide(req("d"), None))
    assert d.classifier == "big" and d.intents == ["web_lookup"] and r.health()[0]["circuit"] == "closed"


def test_all_classifiers_down_fails_closed():
    r = Router(chain=[Entry("a", Flaky(error=OSError())), Entry("b", Flaky(error=OSError()))])
    with pytest.raises(RouterUnavailable):
        run(r.decide(req("x"), None))


def test_degraded_fallback_with_no_match_is_unavailable_not_no_intent():
    r = Router(chain=[Entry("llm", Flaky(error=OSError())), Entry("rules", Flaky([]), degraded=True)])
    with pytest.raises(RouterUnavailable):
        run(r.decide(req("tell me a joke"), None))
    r2 = Router(chain=[Entry("llm", Flaky(error=OSError())), Entry("rules", Flaky(["web_lookup"]), degraded=True)])
    d = run(r2.decide(req("forecast"), None))
    assert d.intents == ["web_lookup"] and d.degraded is True


def test_a_real_empty_answer_from_a_healthy_classifier_is_a_genuine_fallback():
    r = Router(chain=[Entry("llm", Flaky([])), Entry("rules", Flaky(["web_lookup"]), degraded=True)])
    assert run(r.decide(req("hello"), None)).mode == "fallback"             # the healthy model said "no intent": believe it


# ------------------------------------------------------------------ LLM classifier: malformed replies are failures, not "no intent"
def _clf_with(handler):
    clf = LLMClassifier(REG, "http://router.invalid", "t", fewshot=False)
    clf.http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://router.invalid")
    return clf


def _chat(content):
    return lambda request: httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_valid_reply_parses_and_filters_unknown_ids():
    clf = _clf_with(_chat(json.dumps({"intents": ["home_state", "made_up"]})))
    assert clf("lights?", None, {}).intents == ["home_state"]


@pytest.mark.parametrize("content", ["Sure! The intent is home_state.", "", json.dumps({"nope": []}), json.dumps({"intents": "home_state"})])
def test_malformed_reply_raises(content):
    clf = _clf_with(_chat(content))
    with pytest.raises(Exception):
        clf("lights?", None, {})


def test_http_error_raises():
    clf = _clf_with(lambda request: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        clf("lights?", None, {})


# ------------------------------------------------------------------ registry data: router examples + reload
def _copy_registry(tmp_path):
    root = tmp_path / "reg"
    shutil.copytree(ROOT / "registry", root)
    return root


def test_router_examples_are_validated_against_the_registry(tmp_path):
    root = _copy_registry(tmp_path)
    (root / "router_examples.json").write_text(json.dumps({"cross": [{"text": "x and y", "intents": ["home_state", "nonexistent_intent"]}], "none": []}))
    with pytest.raises(registry.RegistryError) as e:
        registry.load(root)
    assert "unknown intent" in str(e.value)
    (root / "router_examples.json").write_text(json.dumps({"cross": [{"text": "only one", "intents": ["home_state"]}], "none": []}))
    with pytest.raises(registry.RegistryError):
        registry.load(root)


def test_classifier_prompt_uses_registry_examples_and_rebuilds_on_reload(tmp_path):
    clf = LLMClassifier(REG, "http://x", "t", fewshot=True)
    assert "Read the latest tech headlines out loud" in clf.system                    # from router_examples.json, not from code
    root = _copy_registry(tmp_path)
    d = json.loads((root / "intents" / "calendar.json").read_text())
    d["description"] = "A brand new description for calendar used to prove the prompt refreshes."
    (root / "intents" / "calendar.json").write_text(json.dumps(d))
    clf.rebuild(registry.load(root))
    assert "prove the prompt refreshes" in clf.system


class Rebuildable(FakeClassifier):
    rebuilt = 0

    def rebuild(self, reg):
        Rebuildable.rebuilt += 1


def test_reload_swaps_registry_rebuilds_classifiers_and_rejects_bad_registry(tmp_path):
    root = _copy_registry(tmp_path)
    s = Settings(state_dir=tmp_path / "state", registry_dir=root, poll_interval_s=0.0)
    clf = Rebuildable({})
    gw = Gateway(s, registry.load(root), Router(clf, "fake"), FakeOC(), SessionStore(tmp_path / "state" / "s.json"))
    Rebuildable.rebuilt = 0
    d = json.loads((root / "intents" / "home_state.json").read_text())
    d["examples"].append("Is the thermostat on a schedule right now")
    (root / "intents" / "home_state.json").write_text(json.dumps(d))

    async def go():
        return await gw.reload()
    out = run(go())
    assert out["intents"] == 11 and Rebuildable.rebuilt == 1
    assert "Is the thermostat on a schedule right now" in gw.reg.intents["home_state"].examples
    good = gw.reg
    (root / "intents" / "home_state.json").write_text("{ not json")
    with pytest.raises(registry.RegistryError):
        run(go())
    assert gw.reg is good and Rebuildable.rebuilt == 1                                # old registry kept, classifiers untouched


# ------------------------------------------------------------------ service: errors are contained
class BrokenOC(FakeOC):
    def __init__(self, fail="create", **kw):
        super().__init__(**kw)
        self.fail = fail

    async def create_session(self, agent, permissions):
        if self.fail == "create":
            raise OpenCodeError("POST /api/session -> HTTP 500")
        return await super().create_session(agent, permissions)

    async def messages(self, sid):
        if self.fail == "messages":
            raise OpenCodeError("GET messages -> HTTP 500")
        return await super().messages(sid)


def _gw(tmp_path, table, oc):
    s = Settings(state_dir=tmp_path, poll_interval_s=0.0, run_timeout_s=5, users_file=write_users(tmp_path))
    return Gateway(s, REG, Router(FakeClassifier(table), "fake"), oc, SessionStore(tmp_path / "sessions.json"))


def test_opencode_down_during_setup_returns_a_clean_error(tmp_path):
    gw = _gw(tmp_path, {"lights?": ["home_state"]}, BrokenOC("create"))
    r = ask(gw, "lights?")
    assert r.status == "error" and r.answer == MSG_BACKEND_DOWN
    assert '"outcome": "error"' in (tmp_path / "traces.jsonl").read_text()


def test_opencode_failure_mid_run_never_leaves_the_session_busy(tmp_path):
    oc = BrokenOC("messages")
    gw = _gw(tmp_path, {"lights?": ["home_state"]}, oc)
    r = ask(gw, "lights?")
    assert r.status == "error" and r.answer == MSG_BACKEND_DOWN
    sid = next(iter(gw.store._data))
    assert gw.store.get(sid).busy is False                                            # a stuck "busy" flag would turn every later message into a steer
    assert SessionStore(tmp_path / "sessions.json").get(sid).busy is False            # ...including after a restart


def test_router_unavailable_returns_clear_error_and_runs_nothing(tmp_path):
    s = Settings(state_dir=tmp_path, poll_interval_s=0.0)
    oc = FakeOC()
    gw = Gateway(s, REG, Router(chain=[Entry("a", Flaky(error=OSError()))]), oc, SessionStore(tmp_path / "sessions.json"))
    r = ask(gw, "lights?")
    assert r.status == "error" and r.answer == MSG_ROUTER_DOWN
    assert not oc.calls                                                               # fail closed: no session, no model run, no tools


def test_bridge_route_reports_errors_as_a_kind_not_an_exception(tmp_path):
    gw = _gw(tmp_path, {"lights?": ["home_state"]}, BrokenOC("create"))
    out = run(gw.route_for_bridge(req("lights?")))
    assert out["kind"] == "error" and out["answer"] == MSG_BACKEND_DOWN


# ------------------------------------------------------------------ concurrency: a second message into a busy session is steered
class HoldingOC(FakeOC):
    """The first turn does not finish until release() is called."""
    def __init__(self):
        super().__init__()
        self.gate = None

    async def prompt(self, sid, text, delivery="queue"):
        if delivery == "queue" and self.gate is None:
            self.calls.append(("prompt", sid, text, delivery))
            self._add(sid, "user", [{"type": "text", "text": text}])
            self.sessions[sid]["time"] = {"idle": 1, "busy": self.msgs[sid][-1]["time"]["created"]}
            self.gate = sid                                                            # running, no answer yet
            return
        await super().prompt(sid, text, delivery)

    def release(self):
        sid = self.gate
        self._add(sid, "assistant", [{"type": "text", "text": "done"}])
        self.sessions[sid]["time"] = {"idle": next(self.clock), "busy": self.msgs[sid][0]["time"]["created"]}


def test_second_message_into_a_running_session_is_steered_not_interleaved(tmp_path):
    oc = HoldingOC()
    gw = _gw(tmp_path, {"lights?": ["home_state"], "only the kitchen": ["home_state"]}, oc)

    async def scenario():
        first = asyncio.create_task(gw.ask(req("lights?")))
        for _ in range(50):                                                            # wait until the turn is running
            await asyncio.sleep(0.01)
            if oc.gate:
                break
        sid = oc.gate
        second = await gw.ask(req("only the kitchen", sid, True))
        oc.release()
        return await first, second
    r1, r2 = run(scenario())
    assert r2.status == "busy_steered" and r2.routing.mode == "steer"
    assert any(c[0] == "prompt" and c[3] == "steer" and c[2] == "only the kitchen" for c in oc.calls)
    assert r1.status == "done" and r1.answer == "done"


# ------------------------------------------------------------------ observability, rotation, pruning
def test_stats_summarise_outcomes_intents_and_unsupported_demand(tmp_path):
    gw, _, _ = make(tmp_path, {"lights?": ["home_state"], "calendar?": ["calendar"]})
    ask(gw, "lights?"); ask(gw, "lights?"); ask(gw, "calendar?")
    st = gw.stats()
    assert st["turns_in_window"] == 3 and st["outcomes"]["ok"] == 2 and st["outcomes"]["unsupported"] == 1
    assert st["intents"]["home_state"] == 2
    assert "calendar.list_events" in st["unsupported_demand"]                         # what people ask for that is not built yet
    assert st["router"][0]["circuit"] == "closed" and st["sessions"] >= 2


def test_trace_file_rotates_when_large(tmp_path, monkeypatch):
    monkeypatch.setattr(service_mod, "TRACE_MAX_BYTES", 400)
    gw, _, _ = make(tmp_path, {"lights?": ["home_state"]})
    for _ in range(8):
        ask(gw, "lights?")
    assert (tmp_path / "traces.1.jsonl").exists()
    assert (tmp_path / "traces.jsonl").stat().st_size < 3000


def test_session_pruning_removes_idle_and_caps_count(tmp_path):
    store = SessionStore(tmp_path / "s.json")
    now = datetime(2026, 11, 8, tzinfo=timezone.utc)
    for n, age in enumerate([1, 5, 40, 90]):
        store.put(SessionState(session_id=f"s{n}", created_at=(now - timedelta(days=age)).isoformat()))
    assert store.prune(max_age_days=30, now=now) == 2 and store.count() == 2
    assert SessionStore(tmp_path / "s.json").count() == 2                              # persisted
    assert store.prune(max_age_days=30, max_sessions=1, now=now) == 1 and store.get("s0") is not None   # the newest survives


# ------------------------------------------------------------------ OpenCode client retries only safe reads
def _client(handler):
    return OpenCodeClient("http://oc.invalid", "pw", "/tmp", transport=httpx.MockTransport(handler))


def test_get_is_retried_on_server_errors_then_succeeds():
    n = {"c": 0}

    def handler(request):
        n["c"] += 1
        return httpx.Response(503) if n["c"] < 3 else httpx.Response(200, json={"data": [{"name": "gmail", "status": {"status": "connected"}}]})
    assert run(_client(handler).mcp_status()) == {"gmail": "connected"} and n["c"] == 3


def test_post_is_never_retried():
    n = {"c": 0}

    def handler(request):
        n["c"] += 1
        return httpx.Response(503)
    with pytest.raises(OpenCodeError):
        run(_client(handler).create_session("royva", []))
    assert n["c"] == 1                                                                 # a retried create could duplicate a session


def test_get_gives_up_after_three_transport_failures():
    def handler(request):
        raise httpx.ConnectError("refused")
    with pytest.raises(OpenCodeError):
        run(_client(handler).mcp_status())


# ------------------------------------------------------------------ token auth
def test_token_required_only_when_configured(tmp_path):
    from fastapi import HTTPException
    from royva_gateway import app as app_mod
    gw, _, _ = make(tmp_path, {})
    app_mod.app.state.gw = gw
    run(app_mod.require_token(authorization=""))                                       # no token configured: open
    gw.s.token = "s3cret"
    with pytest.raises(HTTPException):
        run(app_mod.require_token(authorization=""))
    with pytest.raises(HTTPException):
        run(app_mod.require_token(authorization="Bearer nope"))
    run(app_mod.require_token(authorization="Bearer s3cret"))


# ------------------------------------------------------------------ generated context stays generic
def test_speakers_text_is_generated_from_media_players_not_hardcoded():
    from royva_gateway import home_context
    ctx = home_context.build_from({"floors": {}, "areas": {}}, {"latitude": 1.0, "longitude": 2.0}, "", ["pat"], "pat", ["Kitchen Speaker", "Den TV", "Kitchen Speaker"])
    assert "Den TV, Kitchen Speaker." in ctx["speakers"] and ctx["speakers"].count("Kitchen Speaker") == 1
    assert "speakers" not in home_context.build_from({"floors": {}, "areas": {}}, {}, "", [], "")


def test_static_context_fallbacks_contain_no_household_or_brand_specifics():
    from royva_gateway import profiles
    text = " ".join(profiles.PROVIDER_TEXT.values()).lower()
    assert "sonos" not in text and "airplay" not in text and "four" not in text


# ------------------------------------------------------------------ readiness is continuous (OpenCode can restart underneath the gateway)
def test_readiness_follows_the_live_mcp_status(tmp_path):
    gw, oc, _ = make(tmp_path, {})
    assert gw.ready is False
    assert run(gw.check_ready_once()) is True and gw.ready is True
    oc.mcp = {"home-assistant": "connected", "gmail": "connecting", "ha-history": "connected", "ha-entity-history": "connected", "ha-speakers": "connected", "ha-routines": "connected"}   # OpenCode restarted
    assert run(gw.check_ready_once()) is False and gw.ready is False                  # requests get 503 instead of running with missing tools
    oc.mcp = {"home-assistant": "connected", "gmail": "connected", "ha-history": "connected", "ha-entity-history": "connected", "ha-speakers": "connected", "ha-routines": "connected"}
    assert run(gw.check_ready_once()) is True


def test_readiness_is_false_when_opencode_is_unreachable(tmp_path):
    gw, oc, _ = make(tmp_path, {})
    run(gw.check_ready_once())
    async def boom():
        raise OpenCodeError("connection refused")
    oc.mcp_status = boom
    assert run(gw.check_ready_once()) is False and gw.ready is False


def test_router_clips_huge_messages_but_keeps_both_ends():
    from royva_gateway.classifiers import clip, MAX_ROUTER_CHARS
    text = "START " + "x" * 50000 + " END"
    out = clip(text, MAX_ROUTER_CHARS)
    assert len(out) <= MAX_ROUTER_CHARS + 10 and out.startswith("START") and out.endswith("END")
    assert clip("short", 100) == "short"
