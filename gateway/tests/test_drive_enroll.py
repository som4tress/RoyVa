"""Per-person Google Drive enrollment: the same sign-in flow as Gmail, a separate read-only token, a separate account list and a separate server per person."""
import json
import os
import stat
from urllib.parse import urlparse, parse_qs

import pytest

from royva_gateway.gmail_enroll import Enroller, EnrollError

CLIENT = {"web": {"client_id": "cid.apps", "client_secret": "sek", "redirect_uris": ["https://example.github.io/relay/"]}}
DRIVE_READ = "https://www.googleapis.com/auth/drive.readonly"
GMAIL_READ = "https://www.googleapis.com/auth/gmail.readonly"


class Google:
    def __init__(self, refresh="r-1", scope=DRIVE_READ, email="dummy@example.com"):
        self.calls, self.refresh, self.scope, self.email = [], refresh, scope, email

    def __call__(self, method, url, data=None, headers=None):
        self.calls.append((method, url, data))
        if url.endswith("/token"):
            out = {"access_token": "a-1", "expires_in": 3600, "scope": self.scope, "token_type": "Bearer"}
            if self.refresh:
                out["refresh_token"] = self.refresh
            return out
        if "/drive/v3/about" in url:
            return {"user": {"emailAddress": self.email}}
        if url.endswith("/profile"):
            return {"emailAddress": self.email}
        return {}


@pytest.fixture
def env(tmp_path):
    cf = tmp_path / "client.json"; cf.write_text(json.dumps(CLIENT))
    g = Google()
    return Enroller(tmp_path, client_file=cf, http=g, service="drive"), g, tmp_path, cf


def _go(e, person="dummy"):
    url = e.start(person)
    state = parse_qs(urlparse(url).query)["state"][0]
    return e.finish(f"{state}.the-code", person=person)


def test_drive_asks_only_for_read_only_access(env):
    e, g, tmp, cf = env
    q = parse_qs(urlparse(e.start("dummy")).query)
    assert q["scope"] == [DRIVE_READ] and q["access_type"] == ["offline"] and q["code_challenge_method"] == ["S256"]
    assert parse_qs(urlparse(e.start("dummy", manage=True)).query)["scope"] == [DRIVE_READ]          # there is no "manage" for Drive: asking for it changes nothing


def test_finish_stores_the_token_in_its_own_folder_with_private_permissions(env):
    e, g, tmp, cf = env
    r = _go(e)
    assert r == {"person": "dummy", "email": "dummy@example.com", "mode": "readonly"}
    assert (tmp / "drive" / "dummy.credentials.json").exists() and not (tmp / "gmail").exists()
    cred = json.loads((tmp / "drive" / "dummy.credentials.json").read_text())
    assert cred["refresh_token"] == "r-1"
    for f in ((tmp / "drive" / "dummy.credentials.json"), (tmp / "drive" / "dummy.keys.json")):
        assert stat.S_IMODE(os.stat(f).st_mode) == 0o600
    assert any("/drive/v3/about" in c[1] for c in g.calls) and not any(c[1].endswith("/profile") for c in g.calls)       # the account is read from Drive, not Gmail
    assert e.accounts() == {"dummy": e.accounts()["dummy"]} and e.accounts()["dummy"]["email"] == "dummy@example.com"


def test_a_sign_in_without_the_drive_box_ticked_is_refused_and_nothing_is_stored(env):
    e, g, tmp, cf = env
    g.scope = "openid email"
    with pytest.raises(EnrollError, match="Drive access was not granted"):
        _go(e)
    assert e.accounts() == {}
    g.scope = GMAIL_READ                                                              # a Gmail token is not a Drive token
    with pytest.raises(EnrollError, match="Drive access was not granted"):
        _go(e)


def test_no_refresh_token_is_explained(env):
    e, g, tmp, cf = env
    g.refresh = None
    with pytest.raises(EnrollError, match="long-lived"):
        _go(e)


def test_drive_and_gmail_are_independent_for_the_same_person(tmp_path):
    cf = tmp_path / "client.json"; cf.write_text(json.dumps(CLIENT))
    g = Google(scope=GMAIL_READ)
    mail = Enroller(tmp_path, client_file=cf, http=g)                                  # the default service is still Gmail
    url = mail.start("dummy"); mail.finish(f"{parse_qs(urlparse(url).query)['state'][0]}.c", person="dummy")
    g.scope = DRIVE_READ
    drive = Enroller(tmp_path, client_file=cf, http=g, service="drive"); _go(drive)
    assert set(mail.accounts()) == {"dummy"} and set(drive.accounts()) == {"dummy"}
    assert drive.revoke("dummy") is True
    assert mail.accounts() and not drive.accounts()                                    # disconnecting Drive leaves Gmail connected
    assert (tmp_path / "gmail" / "dummy.credentials.json").exists() and not (tmp_path / "drive" / "dummy.credentials.json").exists()


def test_a_sign_in_started_for_gmail_cannot_be_finished_as_drive(tmp_path):
    cf = tmp_path / "client.json"; cf.write_text(json.dumps(CLIENT))
    g = Google(scope=DRIVE_READ)
    mail = Enroller(tmp_path, client_file=cf, http=g); drive = Enroller(tmp_path, client_file=cf, http=g, service="drive")
    state = parse_qs(urlparse(mail.start("dummy")).query)["state"][0]
    assert mail.has_pending(state) and not drive.has_pending(state)
    with pytest.raises(EnrollError, match="not started here"):
        drive.finish(f"{state}.c", person="dummy")


def test_revoke_deletes_the_files_and_tells_google(env):
    e, g, tmp, cf = env
    _go(e)
    assert e.revoke("dummy") is True and e.revoke("dummy") is False
    assert not list((tmp / "drive").glob("dummy.*")) and any("revoke" in c[1] for c in g.calls)


def test_paths_name_the_files_the_drive_server_of_that_person_reads(env):
    e, g, tmp, cf = env
    _go(e)
    assert e.paths("dummy") == {"credentials": str(tmp / "drive" / "dummy.credentials.json"), "keys": str(tmp / "drive" / "dummy.keys.json")}
    assert e.paths("ghost") is None


def test_each_person_gets_a_drive_server_cloned_from_the_base_entry_and_leaving_removes_it(env):
    e, g, tmp, cf = env
    _go(e); _go(e, "alice")
    cfg = tmp / "opencode.json"
    base = {"type": "local", "command": ["/py", "/x/mcp/drive/server.py"], "enabled": False, "codemode": False}
    gmail = {"type": "local", "command": ["node", "g.js"], "environment": {"A": "b"}}
    cfg.write_text(json.dumps({"mcp": {"servers": {"drive": base, "gmail": gmail, "gmail-u-bob": gmail, "drive-u-gone": base}}}))
    assert e.sync_opencode_config(cfg) == ["drive-u-alice", "drive-u-dummy"]
    servers = json.loads(cfg.read_text())["mcp"]["servers"]
    one = servers["drive-u-dummy"]
    assert one["enabled"] is True and one["command"] == base["command"]
    assert one["environment"] == {"DRIVE_OAUTH_KEYS_PATH": str(tmp / "drive" / "dummy.keys.json"), "DRIVE_CREDENTIALS_PATH": str(tmp / "drive" / "dummy.credentials.json")}
    assert "drive-u-gone" not in servers and servers["gmail-u-bob"] == gmail and servers["gmail"] == gmail          # Gmail's servers are untouched
    assert servers["drive"]["enabled"] is False                                         # the base entry never runs: it has no credentials
    e.revoke("alice"); e.sync_opencode_config(cfg)
    assert "drive-u-alice" not in json.loads(cfg.read_text())["mcp"]["servers"]


def test_the_gmail_sync_never_removes_a_drive_server(tmp_path):
    cf = tmp_path / "client.json"; cf.write_text(json.dumps(CLIENT))
    mail = Enroller(tmp_path, client_file=cf, http=Google())
    cfg = tmp_path / "opencode.json"
    cfg.write_text(json.dumps({"mcp": {"servers": {"gmail": {"type": "local", "command": ["n"]}, "drive-u-alice": {"type": "local", "command": ["p"]}}}}))
    mail.sync_opencode_config(cfg)
    assert "drive-u-alice" in json.loads(cfg.read_text())["mcp"]["servers"]


def test_the_command_line_sync_restores_every_persons_servers_after_the_config_was_rendered_again(tmp_path, monkeypatch):
    """deploy renders config/opencode.json from the template, which has no per-person servers: `sync` puts them back."""
    from royva_gateway import gmail_cli
    cf = tmp_path / "client.json"; cf.write_text(json.dumps(CLIENT))
    g = Google(scope=GMAIL_READ)
    mail = Enroller(tmp_path, client_file=cf, http=g); mail.finish(f"{parse_qs(urlparse(mail.start('bob')).query)['state'][0]}.c", person="bob")
    g.scope = DRIVE_READ
    drive = Enroller(tmp_path, client_file=cf, http=g, service="drive"); _go(drive, "alice")
    cfg = tmp_path / "opencode.json"
    entry = {"type": "local", "command": ["x"], "environment": {}}
    cfg.write_text(json.dumps({"mcp": {"servers": {"gmail": entry, "gmail-tidy": entry, "drive": entry}}}))
    class S:
        state_dir = tmp_path
    monkeypatch.setattr(gmail_cli, "Settings", S); monkeypatch.setattr(gmail_cli, "CONFIG", cfg)
    monkeypatch.setenv("ROYVA_GMAIL_CLIENT", str(cf))
    assert gmail_cli.main(["sync"]) == 0
    names = set(json.loads(cfg.read_text())["mcp"]["servers"])
    assert {"gmail-u-bob", "gmail-tidy-u-bob", "drive-u-alice"} <= names
