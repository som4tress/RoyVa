"""Per-person Gmail enrollment: PKCE link, single-use state, token exchange, files, revoke. Google is a fake."""
import json
import os
import stat
from urllib.parse import urlparse, parse_qs

import pytest

from royva_gateway.gmail_enroll import Enroller, EnrollError, SCOPE, SCOPE_READ, SCOPE_READ, SCOPE_MANAGE

CLIENT = {"web": {"client_id": "cid.apps", "client_secret": "sek", "redirect_uris": ["https://example.github.io/relay/"]}}


class Google:
    def __init__(self, refresh="r-1", scope=SCOPE, email="dummy@example.com"):
        self.calls, self.refresh, self.scope, self.email = [], refresh, scope, email

    def __call__(self, method, url, data=None, headers=None):
        self.calls.append((method, url, data))
        if url.endswith("/token"):
            out = {"access_token": "a-1", "expires_in": 3600, "scope": self.scope, "token_type": "Bearer"}
            if self.refresh:
                out["refresh_token"] = self.refresh
            return out
        if url.endswith("/profile"):
            return {"emailAddress": self.email}
        return {}


@pytest.fixture
def env(tmp_path):
    cf = tmp_path / "client.json"; cf.write_text(json.dumps(CLIENT))
    t = [1000.0]
    g = Google()
    return Enroller(tmp_path / "state", cf, http=g, now=lambda: t[0]), g, t


def _state(url):
    return parse_qs(urlparse(url).query)["state"][0]


def test_link_has_pkce_offline_and_never_asks_for_send_or_compose(env):
    e, _, _ = env
    q = parse_qs(urlparse(e.start("dummy")).query)
    assert q["code_challenge_method"] == ["S256"] and q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    assert q["scope"] == [SCOPE_READ] and q["redirect_uri"] == ["https://example.github.io/relay/"]
    assert "send" not in q["scope"][0] and "compose" not in q["scope"][0]


def test_finish_with_relay_string_writes_private_files_and_records_mailbox(env):
    e, g, _ = env
    st = _state(e.start("dummy"))
    r = e.finish(f"{st}.4/0AbC_d-e")
    assert r == {"person": "dummy", "email": "dummy@example.com", "mode": "manage"}   # the fake Google grants the manage scope
    exch = [c for c in g.calls if c[1].endswith("/token")][0][2]
    assert exch["code"] == "4/0AbC_d-e" and exch["code_verifier"] and exch["redirect_uri"] == "https://example.github.io/relay/"
    p = e.paths("dummy")
    for f in p.values():
        assert stat.S_IMODE(os.stat(f).st_mode) == 0o600
    cred = json.load(open(p["credentials"]))
    assert cred["refresh_token"] == "r-1" and cred["expiry_date"] == int((1000 + 3600) * 1000)
    assert json.load(open(p["keys"]))["web"]["client_id"] == "cid.apps"      # token stays paired with its issuing client
    assert e.accounts()["dummy"]["email"] == "dummy@example.com"


def test_full_redirect_url_and_bare_code_are_accepted(env):
    e, _, _ = env
    st = _state(e.start("a"))
    assert e.finish(f"https://example.github.io/relay/?state={st}&code=XYZ&scope=s")["person"] == "a"
    e.start("b")                                                    # only one open request: a bare code is unambiguous
    assert e.finish("BARECODE")["person"] == "b"


def test_state_is_single_use_and_unknown_state_is_rejected(env):
    e, _, _ = env
    st = _state(e.start("dummy"))
    e.finish(f"{st}.c1")
    with pytest.raises(EnrollError):
        e.finish(f"{st}.c1")
    with pytest.raises(EnrollError):
        e.finish("0" * 32 + ".c")


def test_expired_link_is_refused(env):
    e, _, t = env
    st = _state(e.start("dummy"))
    t[0] += 601
    with pytest.raises(EnrollError, match="expired"):
        e.finish(f"{st}.c")


def test_bare_code_with_two_open_requests_is_refused(env):
    e, _, _ = env
    e.start("a"); e.start("b")
    with pytest.raises(EnrollError):
        e.finish("BARE")


def test_missing_refresh_token_and_missing_scope_are_refused_and_nothing_is_stored(tmp_path):
    cf = tmp_path / "c.json"; cf.write_text(json.dumps(CLIENT))
    for g, msg in ((Google(refresh=None), "long-lived"), (Google(scope="openid"), "not granted")):
        e = Enroller(tmp_path / msg.split()[0], cf, http=g, now=lambda: 1.0)
        st = _state(e.start("dummy"))
        with pytest.raises(EnrollError, match=msg):
            e.finish(f"{st}.c")
        assert e.accounts() == {}


def test_bad_person_name_and_missing_client(tmp_path):
    cf = tmp_path / "c.json"; cf.write_text(json.dumps(CLIENT))
    with pytest.raises(EnrollError):
        Enroller(tmp_path, cf).start("../etc")
    with pytest.raises(EnrollError, match="not set up"):
        Enroller(tmp_path, tmp_path / "missing.json").start("dummy")


def test_revoke_deletes_files_and_calls_google(env):
    e, g, _ = env
    st = _state(e.start("dummy")); e.finish(f"{st}.c")
    p = e.paths("dummy")
    assert e.revoke("dummy") is True
    assert not os.path.exists(p["credentials"]) and e.paths("dummy") is None
    assert any(c[1].endswith("/revoke") for c in g.calls)
    assert e.revoke("dummy") is False


def test_sync_adds_a_server_pair_per_person_and_prunes_removed_people(env, tmp_path):
    e, _, _ = env
    cfg = tmp_path / "opencode.json"
    cfg.write_text(json.dumps({"mcp": {"servers": {
        "gmail": {"command": ["node", "x"], "environment": {"GMAIL_CREDENTIALS_PATH": "/owner/c.json"}},
        "gmail-tidy": {"command": ["py", "t"], "environment": {"GMAIL_CREDENTIALS_PATH": "/owner/c.json"}},
        "gmail-u-stale": {"command": ["old"]}, "gmail-tidy-u-stale": {"command": ["old"]}, "ha-history": {"command": ["h"]}}}}))
    st = _state(e.start("dummy")); e.finish(f"{st}.c")
    assert e.sync_opencode_config(cfg) == ["gmail-tidy-u-dummy", "gmail-u-dummy"]
    s = json.loads(cfg.read_text())["mcp"]["servers"]
    assert set(s) == {"gmail", "gmail-tidy", "gmail-u-dummy", "gmail-tidy-u-dummy", "ha-history"}
    assert s["gmail-u-dummy"]["environment"]["GMAIL_CREDENTIALS_PATH"] == e.paths("dummy")["credentials"]
    assert s["gmail"]["environment"]["GMAIL_CREDENTIALS_PATH"] == "/owner/c.json"       # the original account is untouched
    e.revoke("dummy"); e.sync_opencode_config(cfg)
    assert set(json.loads(cfg.read_text())["mcp"]["servers"]) == {"gmail", "gmail-tidy", "ha-history"}


def test_reserved_names_are_refused(env):
    e, _, _ = env
    for n in ("default", "a_b", "", "-x"):
        with pytest.raises(EnrollError):
            e.start(n)


def test_default_is_read_only_and_manage_must_be_asked_for(env):
    e, g, t = env
    assert parse_qs(urlparse(e.start("a")).query)["scope"] == [SCOPE_READ]
    assert parse_qs(urlparse(e.start("b", manage=True)).query)["scope"] == [SCOPE_MANAGE]


def test_mode_comes_from_the_scope_google_actually_granted(tmp_path):
    cf = tmp_path / "c.json"; cf.write_text(json.dumps(CLIENT))
    for granted, mode in ((SCOPE_READ, "readonly"), (SCOPE_MANAGE, "manage")):
        e = Enroller(tmp_path / granted[-8:], cf, http=Google(scope=granted), now=lambda: 1000.0)
        r = e.finish(_state(e.start("dummy")) + ".code1")
        assert r["mode"] == mode and e.accounts()["dummy"]["mode"] == mode


def test_manage_requested_but_only_read_granted_is_refused(tmp_path):
    cf = tmp_path / "c.json"; cf.write_text(json.dumps(CLIENT))
    e = Enroller(tmp_path / "s", cf, http=Google(scope=SCOPE_READ), now=lambda: 1000.0)
    with pytest.raises(EnrollError):
        e.finish(_state(e.start("dummy", manage=True)) + ".code1")
    assert e.accounts() == {}


def test_one_user_cannot_redeem_another_users_sign_in(env):
    e, g, t = env
    url = e.start("alice")
    with pytest.raises(EnrollError):
        e.finish(_state(url) + ".code1", person="bob")             # bob pastes alice's string
    assert e.accounts() == {}
    # and a bare code is matched to the asking user's own pending request only
    e.start("alice"); e.start("bob")
    assert e.finish("barecode", person="bob")["person"] == "bob"
