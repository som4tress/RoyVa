"""HTTP layer: readiness gate, request validation, token auth, stats, atomic reload."""
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from royva_gateway import app as app_mod, registry
from royva_gateway.config import Settings
from royva_gateway.router import Router
from royva_gateway.service import Gateway
from royva_gateway.sessions import SessionStore

from test_gateway import FakeClassifier, FakeOC, ROOT, write_users


def client(tmp_path, table=None, ready=True, token="", registry_dir=None):
    s = Settings(state_dir=tmp_path / "state", poll_interval_s=0.0, run_timeout_s=5, token=token, registry_dir=registry_dir or (ROOT / "registry"), users_file=write_users(tmp_path))
    gw = Gateway(s, registry.load(s.registry_dir), Router(FakeClassifier(table or {}), "fake"), FakeOC(), SessionStore(tmp_path / "state" / "s.json"))
    gw.ready = ready
    app_mod.app.state.gw = gw
    return TestClient(app_mod.app), gw                                  # no `with`: the real lifespan (which builds real clients) is not started


BODY = {"text": "lights?", "user": "telegram:1"}


def test_requests_get_503_until_ready_but_healthz_still_answers(tmp_path):
    c, _ = client(tmp_path, {"lights?": ["home_state"]}, ready=False)
    assert c.post("/v1/ask", json=BODY).status_code == 503
    assert c.post("/v1/route", json=BODY).status_code == 503
    assert c.post("/v1/session").status_code == 503
    h = c.get("/healthz").json()
    assert h["ready"] is False and h["router"][0]["circuit"] == "closed"


def test_ask_happy_path_matches_the_contract(tmp_path):
    c, _ = client(tmp_path, {"lights?": ["home_state"]})
    r = c.post("/v1/ask", json=BODY)
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "done" and j["routing"]["intents"] == ["home_state"] and j["session_id"]


def test_bridge_endpoints_session_then_route(tmp_path):
    c, _ = client(tmp_path, {"lights?": ["home_state"]})
    sid = c.post("/v1/session").json()["session_id"]
    out = c.post("/v1/route", json={**BODY, "session_id": sid}).json()
    assert out["kind"] == "run" and out["session_id"] == sid and out["cap"] == 6 and out["prompt"].endswith("lights?")


@pytest.mark.parametrize("bad", [{"text": "", "user": "u"}, {"user": "u"}, {"text": "x"}, {"text": "x", "user": "u", "extra": 1},
                                 {"text": "x", "user": "u", "is_reply": True}, {"text": "y" * 9000, "user": "u"}])
def test_invalid_requests_are_rejected_with_422(tmp_path, bad):
    c, _ = client(tmp_path)
    assert c.post("/v1/ask", json=bad).status_code == 422


def test_token_protects_v1_but_not_healthz(tmp_path):
    c, _ = client(tmp_path, {"lights?": ["home_state"]}, token="s3cret")
    assert c.post("/v1/ask", json=BODY).status_code == 401
    assert c.post("/v1/ask", json=BODY, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.post("/v1/ask", json=BODY, headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert c.get("/v1/stats").status_code == 401
    assert c.get("/healthz").status_code == 200                           # liveness stays open for supervisors


def test_stats_endpoint_reports_turns(tmp_path):
    c, _ = client(tmp_path, {"lights?": ["home_state"]})
    c.post("/v1/ask", json=BODY)
    st = c.get("/v1/stats").json()
    assert st["turns_in_window"] == 1 and st["intents"] == {"home_state": 1}


def test_reload_applies_valid_changes_and_rejects_invalid_ones_with_400(tmp_path):
    root = tmp_path / "reg"
    shutil.copytree(ROOT / "registry", root)
    c, gw = client(tmp_path, {}, registry_dir=root)
    assert c.post("/v1/reload").status_code == 200
    d = json.loads((root / "intents" / "home_state.json").read_text())
    d["profile"]["tools"].append("ha.nonexistent_tool")                   # unsafe/invalid edit
    (root / "intents" / "home_state.json").write_text(json.dumps(d))
    before = gw.reg
    r = c.post("/v1/reload")
    assert r.status_code == 400 and "not in the catalog" in json.dumps(r.json())
    assert gw.reg is before                                               # the running registry was not replaced


def test_route_table_is_exactly_the_documented_api():
    """Guards against an edit silently dropping (or adding) an endpoint: the bridge depends on /v1/session and /v1/route."""
    have = {(m, r.path) for r in app_mod.app.routes if hasattr(r, "methods") for m in r.methods if m not in ("HEAD", "OPTIONS")}
    api = {(m, p) for m, p in have if (p.startswith("/v1") and not p.startswith(("/v1/enroll", "/v1/admin"))) or p == "/healthz"}     # enrollment is pinned below
    assert api == {("GET", "/healthz"), ("GET", "/v1/registry"), ("GET", "/v1/stats"),
                   ("POST", "/v1/ask"), ("POST", "/v1/session"), ("POST", "/v1/route"), ("POST", "/v1/reload")}


def test_enrollment_route_table_is_pinned():
    from royva_gateway.app import app
    have = {r.path for r in app.routes}
    for path in ("/v1/enroll/allowed", "/v1/enroll/invite", "/v1/enroll/join", "/v1/enroll/decide", "/v1/enroll/people",
                 "/v1/enroll/revoke", "/v1/enroll/gmail/start", "/v1/enroll/gmail/finish", "/v1/enroll/gmail/stop", "/v1/enroll/is-signin", "/v1/admin/restart-opencode"):
        assert path in have
