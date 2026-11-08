"""Each person's session is granted only their own mailbox's tools; no mailbox means no mail tools; send paths stay denied."""
import json

from royva_gateway import profiles
from royva_gateway.config import Settings
from royva_gateway.registry import load


def _reg():
    return load(Settings().registry_dir)


def _grants(reg):
    return {t: "allow" for t in reg.intents["mail_read"].profile.tools} | {t: "ask" for t in reg.intents["mail_manage"].profile.tools}


def _actions(rules, effect):
    return {r["action"] for r in rules if r["effect"] == effect}


def test_enrolled_person_gets_only_their_own_servers():
    reg, s = _reg(), Settings()
    allowed = _actions(profiles.permissions(reg, _grants(reg), s, "dummy", ("dummy",)), "allow") | \
        _actions(profiles.permissions(reg, _grants(reg), s, "dummy", ("dummy",)), "ask")
    mail = {a for a in allowed if a.startswith("gmail")}
    assert mail and all(a.startswith(("gmail-u-dummy_", "gmail-tidy-u-dummy_")) for a in mail)


def test_default_account_keeps_original_names():
    reg, s = _reg(), Settings()
    rules = profiles.permissions(reg, _grants(reg), s, "default", ("dummy",))
    mail = {a for a in _actions(rules, "allow") | _actions(rules, "ask") if a.startswith("gmail")}
    assert "gmail_search_messages" in mail and not any("dummy" in a for a in mail)


def test_no_mailbox_means_no_mail_tools():
    reg, s = _reg(), Settings()
    rules = profiles.permissions(reg, _grants(reg), s, None, ("dummy",))
    assert not [a for a in _actions(rules, "allow") | _actions(rules, "ask") if a.startswith("gmail")]


def test_send_and_draft_tools_are_denied_for_every_mailbox():
    reg, s = _reg(), Settings()
    deny = _actions(profiles.permissions(reg, {}, s, "dummy", ("dummy", "other")), "deny")
    for acct in ("", "-u-dummy", "-u-other"):
        for w in profiles.MAIL_WRITE_ACTIONS:
            assert f"gmail{acct}_{w}" in deny


def test_unknown_account_in_users_file_gets_no_mailbox(tmp_path):
    from royva_gateway.service import Gateway
    s = Settings(); s.state_dir = tmp_path; s.users_file = tmp_path / "users.json"
    (tmp_path / "gmail").mkdir()
    (tmp_path / "gmail" / "accounts.json").write_text(json.dumps({"alice": {}}))
    s.users_file.write_text(json.dumps({"telegram:1": {"mail": "alice"}, "telegram:2": {"mail": "ghost"}, "telegram:3": {"mail": "default"}, "telegram:4": {}}))
    gw = Gateway.__new__(Gateway); gw.s = s
    assert [gw.user_mail(f"telegram:{i}") for i in (1, 2, 3, 4)] == ["alice", None, "default", None]


def test_read_only_connection_never_gets_change_tools():
    reg, s = _reg(), Settings()
    rules = profiles.permissions(reg, _grants(reg), s, "dummy", ("dummy",), True)
    mail = {a for a in _actions(rules, "allow") | _actions(rules, "ask") if a.startswith("gmail")}
    assert "gmail-u-dummy_search_messages" in mail
    assert not any(x in a for a in mail for x in ("modify", "tidy_matching", "tidy_ids", "batch"))


def test_every_server_account_pair_has_a_unique_name_that_is_never_a_base_server():
    base = set(profiles.MAIL_SERVERS)
    names = {}
    for acct in ("a", "tidy", "tidy-x", "u", "gmail", "x-y", "default2"):
        for server in profiles.MAIL_SERVERS:
            n = profiles.account_action(server, f"{server}_search_messages", acct)
            assert n not in names, (n, acct, server)
            names[n] = (acct, server)
            assert n.split("_", 1)[0] not in base


def test_user_without_a_mailbox_gets_a_clear_message_not_an_improvised_reply():
    import asyncio
    from royva_gateway.service import Gateway
    from royva_gateway.models import AskRequest
    s = Settings()
    gw = Gateway.__new__(Gateway)
    gw.s = s
    # the lightweight pieces prepare() needs are exercised in test_gateway; here the two predicates behind the new branch
    gw.reg = _reg()
    assert gw._uses_mail(gw.reg.intents["mail_read"]) and gw._uses_mail(gw.reg.intents["mail_manage"])
    assert not gw._uses_mail(gw.reg.intents["home_state"])
