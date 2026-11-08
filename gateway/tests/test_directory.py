"""Enrollment directory: owner-only actions, single-use codes, approval, least privilege, Gmail binding, revoke."""
import json

import pytest

from royva_gateway.directory import Directory, DirectoryError
from royva_gateway.gmail_enroll import Enroller

OWNER, ALICE, EVE = "telegram:1", "telegram:2", "telegram:3"


class FakeEnroller(Enroller):
    def __init__(self, state_dir, email="alice@example.com"):
        super().__init__(state_dir, client_file=state_dir / "nope.json")
        self._email, self.started, self.revoked = email, [], []
        self._acct = {}

    def start(self, person, manage=False):
        self.started.append((person, manage)); return f"https://google/auth?for={person}"

    def finish(self, pasted, person=None):
        if "bad" in pasted:
            from royva_gateway.gmail_enroll import EnrollError
            raise EnrollError("sign-in was not started for you")
        self._acct[person] = {"email": self._email, "mode": "readonly"}
        return {"person": person, "email": self._email, "mode": "readonly"}

    def accounts(self):
        return self._acct

    def revoke(self, person):
        self.revoked.append(person); return self._acct.pop(person, None) is not None

    def sync_opencode_config(self, path):
        return []


@pytest.fixture
def d(tmp_path):
    uf = tmp_path / "users.json"
    uf.write_text(json.dumps({OWNER: {"person": "boss", "scopes": ["*"], "mail": "default"}, "_policy": {"silent_scopes": ["gmail"]}}))
    t = [1000.0]
    dd = Directory(uf, tmp_path, FakeEnroller(tmp_path), None, now=lambda: t[0])
    dd.t = t
    return dd


def _enroll(d, who=ALICE, name="alice", email=None):
    code = d.invite(OWNER, name, email)["code"]
    d.join(who, "Alice A", code)
    d.decide(OWNER, name, True)


def test_only_the_owner_can_invite_list_decide_or_revoke(d):
    _enroll(d)
    for call in (lambda: d.invite(ALICE, "bob"), lambda: d.people(ALICE), lambda: d.pending(ALICE),
                 lambda: d.decide(ALICE, "alice", True), lambda: d.revoke(ALICE, "boss")):
        with pytest.raises(DirectoryError, match="owner"):
            call()


def test_join_waits_for_approval_and_grants_nothing_until_then(d):
    code = d.invite(OWNER, "alice")["code"]
    d.join(ALICE, "Alice", code)
    assert not d.is_active(ALICE) and d.active_ids() == ["1"]
    assert [p["name"] for p in d.pending(OWNER)] == ["alice"]
    d.decide(OWNER, "alice", True)
    assert d.is_active(ALICE) and set(d.active_ids()) == {"1", "2"}


def test_approved_member_has_least_privilege_and_decline_grants_nothing(d):
    _enroll(d)
    u = d.users()[ALICE]
    assert u["role"] == "member" and u["scopes"] == [] and "mail" not in u
    code = d.invite(OWNER, "eve")["code"]; d.join(EVE, "Eve", code); d.decide(OWNER, "eve", False)
    assert not d.is_active(EVE)


def test_code_is_single_use_expires_and_errors_are_generic(d):
    code = d.invite(OWNER, "alice")["code"]
    d.join(ALICE, "A", code)
    with pytest.raises(DirectoryError, match="not valid"):
        d.join(EVE, "E", code)                                   # reused
    code2 = d.invite(OWNER, "bob")["code"]
    d.t[0] += 24 * 3600 + 1
    with pytest.raises(DirectoryError, match="not valid"):
        d.join(EVE, "E", code2)                                  # expired
    with pytest.raises(DirectoryError, match="not valid"):
        d.join(EVE, "E", "ZZZZ-ZZZZ")                            # never existed: same message


def test_wrong_codes_are_rate_limited(d):
    for _ in range(5):
        with pytest.raises(DirectoryError):
            d.join(EVE, "E", "AAAA-AAAA")
    good = d.invite(OWNER, "eve")["code"]
    with pytest.raises(DirectoryError, match="Too many"):
        d.join(EVE, "E", good)                                   # even a valid code is refused while limited
    d.t[0] += 601
    d.join(EVE, "E", good)


def test_invite_rejects_bad_names_duplicates_and_bad_email(d):
    for bad in ("", "Bad Name", "a_b", "default"):
        with pytest.raises(DirectoryError):
            d.invite(OWNER, bad)
    _enroll(d)
    with pytest.raises(DirectoryError, match="already"):
        d.invite(OWNER, "alice")
    with pytest.raises(DirectoryError, match="Gmail"):
        d.invite(OWNER, "bob", "not-an-email")


def test_connecting_gmail_sets_mail_and_email_scope_for_that_person_only(d):
    _enroll(d)
    assert d.gmail_start(ALICE) .startswith("https://google/auth?for=alice")
    r = d.gmail_finish(ALICE, "abc.def")
    assert r["email"] == "alice@example.com" and r["needs_restart"]
    u = d.users()[ALICE]
    assert u["mail"] == "alice" and "gmail" in u["scopes"]
    assert d.users()[OWNER]["mail"] == "default"                 # untouched
    with pytest.raises(DirectoryError, match="not enrolled"):
        d.gmail_start(EVE)


def test_expected_email_mismatch_connects_nothing(d):
    _enroll(d, email="someone-else@example.com")
    d.gmail_start(ALICE)
    with pytest.raises(DirectoryError, match="not the one you were invited with"):
        d.gmail_finish(ALICE, "abc.def")
    assert "mail" not in d.users()[ALICE] and "alice" in d.enroller.revoked


def test_revoke_removes_access_gmail_and_open_invites_but_never_the_owner(d):
    _enroll(d); d.gmail_start(ALICE); d.gmail_finish(ALICE, "abc.def")
    r = d.revoke(OWNER, "alice")
    assert r["mailbox_removed"] and not d.is_active(ALICE) and "alice" in d.enroller.revoked
    with pytest.raises(DirectoryError, match="owner cannot"):
        d.revoke(OWNER, "boss")
    assert d.users()["_policy"] == {"silent_scopes": ["gmail"]}          # unrelated settings survive every write


def test_signin_text_detection_and_people_listing(d):
    _enroll(d)
    assert d.looks_like_signin("http://localhost:3000/oauth2callback?state=ab&code=4/0x&scope=s")
    assert d.looks_like_signin("0123456789abcdef0123456789abcdef.4/0Abc")
    assert not d.looks_like_signin("how many unread emails do I have?")
    names = {p["name"]: p for p in d.people(OWNER)}
    assert names["boss"]["role"] == "owner" and names["alice"]["role"] == "member" and names["alice"]["mail"] is None


def test_member_can_disconnect_their_own_gmail_but_not_the_owners(d):
    _enroll(d); d.gmail_start(ALICE); d.gmail_finish(ALICE, "abc.def")
    r = d.gmail_stop(ALICE)
    u = d.users()[ALICE]
    assert r["had_connection"] and "mail" not in u and "gmail" not in u["scopes"] and "alice" in d.enroller.revoked
    with pytest.raises(DirectoryError, match="owner's original"):
        d.gmail_stop(OWNER)
    with pytest.raises(DirectoryError, match="not enrolled"):
        d.gmail_stop(EVE)
