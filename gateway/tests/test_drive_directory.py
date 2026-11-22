"""A member connects their own Google Drive from chat: same rules as Gmail (enrolled only, owner told, wrong account undone), a separate scope, and removal on revoke."""
import json

import pytest

from royva_gateway.directory import Directory, DirectoryError
from royva_gateway.gmail_enroll import Enroller, EnrollError

OWNER, ALICE, EVE = "telegram:1", "telegram:2", "telegram:3"


class Fake(Enroller):
    def __init__(self, state_dir, service, email="alice@example.com"):
        super().__init__(state_dir, client_file=state_dir / "nope.json", service=service)
        self._email, self.started, self.revoked, self.synced, self._acct, self.pending = email, [], [], [], {}, set()

    def start(self, person, manage=False):
        state = f"{len(self.started):032x}"; self.pending.add(state); self.started.append((person, manage)); return f"https://google/auth?for={person}&s={self.service}"

    def has_pending(self, state):
        return state in self.pending

    def finish(self, pasted, person=None):
        if "bad" in pasted:
            raise EnrollError("sign-in was not started for you")
        self._acct[person] = {"email": self._email, "mode": "readonly"}
        return {"person": person, "email": self._email, "mode": "readonly"}

    def accounts(self):
        return self._acct

    def revoke(self, person):
        self.revoked.append(person); return self._acct.pop(person, None) is not None

    def sync_opencode_config(self, path):
        self.synced.append(str(path)); return []


@pytest.fixture
def d(tmp_path):
    uf = tmp_path / "users.json"
    uf.write_text(json.dumps({OWNER: {"person": "boss", "scopes": ["*"], "mail": "default"}}))
    dd = Directory(uf, tmp_path, Fake(tmp_path, "gmail"), tmp_path / "opencode.json", now=lambda: 1000.0, drive_enroller=Fake(tmp_path, "drive"))
    return dd


def _enroll(d, who=ALICE, name="alice", email=None):
    code = d.invite(OWNER, name, email)["code"]
    d.join(who, "Alice A", code)
    d.decide(OWNER, name, True)


def test_an_enrolled_member_gets_a_drive_sign_in_link_a_stranger_does_not(d):
    _enroll(d)
    assert "s=drive" in d.drive_start(ALICE)
    assert d.drive_enroller.started == [("alice", False)]
    with pytest.raises(DirectoryError, match="not enrolled"):
        d.drive_start(EVE)


def test_the_owner_connects_drive_like_everyone_else(d):
    assert "s=drive" in d.drive_start(OWNER)


def test_finishing_connects_only_drive_and_gives_the_drive_scope(d):
    _enroll(d)
    url = d.drive_start(ALICE)
    state = d.drive_enroller.started and next(iter(d.drive_enroller.pending))
    r = d.finish_signin(ALICE, f"{state}.code")
    assert r["service"] == "drive" and r["name"] == "alice" and r["email"] == "alice@example.com" and r["needs_restart"] and r["owners"] == ["1"]
    u = d.users()[ALICE]
    assert u["drive"] == "alice" and "mail" not in u and u["scopes"] == []          # Drive is gated by the person's own connection, not by a scope


def test_a_pasted_code_goes_to_the_service_whose_sign_in_it_belongs_to(d):
    _enroll(d)
    d.gmail_start(ALICE)
    gstate = next(iter(d.enroller.pending))
    r = d.finish_signin(ALICE, f"{gstate}.code")
    assert r["service"] == "gmail" and d.users()[ALICE]["mail"] == "alice" and "drive" not in d.users()[ALICE]
    d.drive_start(ALICE)
    dstate = next(iter(d.drive_enroller.pending))
    assert d.finish_signin(ALICE, f"{dstate}.code")["service"] == "drive"
    u = d.users()[ALICE]
    assert u["mail"] == "alice" and u["drive"] == "alice" and "gmail" in u["scopes"]


def test_a_failed_sign_in_changes_nothing(d):
    _enroll(d)
    d.drive_start(ALICE)
    state = next(iter(d.drive_enroller.pending))
    with pytest.raises(DirectoryError, match="not started"):
        d.finish_signin(ALICE, f"{state}.bad")
    assert "drive" not in d.users()[ALICE]


def test_the_wrong_google_account_is_undone(d):
    _enroll(d, email="alice@example.com")
    d.drive_enroller._email = "someone-else@example.com"
    d.drive_start(ALICE)
    state = next(iter(d.drive_enroller.pending))
    with pytest.raises(DirectoryError, match="not the one you were invited with"):
        d.finish_signin(ALICE, f"{state}.code")
    assert d.drive_enroller.revoked == ["alice"] and "drive" not in d.users()[ALICE]


def test_disconnecting_drive_keeps_gmail(d):
    _enroll(d)
    d.gmail_start(ALICE); d.finish_signin(ALICE, f"{next(iter(d.enroller.pending))}.c")
    d.drive_start(ALICE); d.finish_signin(ALICE, f"{next(iter(d.drive_enroller.pending))}.c")
    r = d.drive_stop(ALICE)
    assert r["had_connection"] is True
    u = d.users()[ALICE]
    assert "drive" not in u and u["mail"] == "alice" and "gmail" in u["scopes"]
    assert d.drive_stop(ALICE)["had_connection"] is False


def test_a_removed_member_loses_the_drive_connection_too(d):
    _enroll(d)
    d.drive_start(ALICE); d.finish_signin(ALICE, f"{next(iter(d.drive_enroller.pending))}.c")
    r = d.revoke(OWNER, "alice")
    assert d.drive_enroller.revoked == ["alice"] and r["drive_removed"] is True


def test_people_shows_who_has_drive(d):
    _enroll(d)
    assert {p["name"]: p.get("drive") for p in d.people(OWNER)}["alice"] is False
    d.drive_start(ALICE); d.finish_signin(ALICE, f"{next(iter(d.drive_enroller.pending))}.c")
    assert {p["name"]: p.get("drive") for p in d.people(OWNER)}["alice"] is True


def test_connecting_rewrites_the_opencode_config_for_both_services(d):
    _enroll(d)
    d.drive_start(ALICE); d.finish_signin(ALICE, f"{next(iter(d.drive_enroller.pending))}.c")
    assert d.drive_enroller.synced and d.enroller.synced                      # one restart picks up whatever changed
