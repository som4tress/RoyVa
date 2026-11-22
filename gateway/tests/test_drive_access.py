"""Google Drive access: tools and skill in the registry, a person's session gets only THEIR Drive server, no connection means a clear message, and file questions never go to Gmail."""
import json
from pathlib import Path

from royva_gateway import profiles, registry
from royva_gateway.config import Settings
from royva_gateway.router import document_not_mail, drive_not_mail

ROOT = Path(__file__).resolve().parent.parent
REG = registry.load(ROOT / "registry")
TOOLS = {"drive.search_files": "drive_search_files", "drive.list_folder": "drive_list_folder", "drive.read_file": "drive_read_file", "drive.find_in_file": "drive_find_in_file"}


def _actions(rules, effect):
    return {r["action"] for r in rules if r["effect"] == effect}


def test_the_drive_tools_are_in_the_catalog_read_only():
    for tid, action in TOOLS.items():
        t = REG.tools[tid]
        assert t.action == action and t.server == "drive" and t.risk == "read" and t.available and not t.scope


def test_the_drive_skill_is_read_only_and_has_no_mail_or_write_tools():
    i = REG.intents["drive_search"]
    assert i.status == "active" and i.profile.write_policy == "read_only" and set(i.profile.tools) == set(TOOLS)
    assert len(i.examples) >= 10 and any("new files" in e.lower() or "this week" in e.lower() for e in i.examples) and any("named" in e.lower() or "called" in e.lower() for e in i.examples)
    assert any("email" in n.lower() for n in i.negatives)
    for mail in ("mail_read", "mail_manage"):
        assert any("drive" in n.lower() for n in REG.intents[mail].negatives), mail
    assert any("drive" in n.lower() for n in REG.intents["document_read"].negatives)


def test_a_person_gets_only_their_own_drive_server():
    grants = {t: "allow" for t in REG.intents["drive_search"].profile.tools}
    rules = profiles.permissions(REG, grants, Settings(), None, (), False, drive_account="alice")
    drive = {a for a in _actions(rules, "allow") if a.startswith("drive")}
    assert drive == {f"drive-u-alice_{a.split('_', 1)[1]}" for a in TOOLS.values()}


def test_no_drive_connection_means_no_drive_tools_and_the_base_name_is_never_granted():
    grants = {t: "allow" for t in REG.intents["drive_search"].profile.tools}
    assert not [a for a in _actions(profiles.permissions(REG, grants, Settings(), None, (), False), "allow") if a.startswith("drive")]
    assert not [a for a in _actions(profiles.permissions(REG, grants, Settings(), None, (), False, drive_account="x"), "allow") if a in TOOLS.values()]


def test_the_gateway_knows_which_drive_belongs_to_whom(tmp_path):
    from royva_gateway.service import Gateway
    s = Settings(); s.state_dir = tmp_path; s.users_file = tmp_path / "users.json"
    (tmp_path / "drive").mkdir()
    (tmp_path / "drive" / "accounts.json").write_text(json.dumps({"alice": {}}))
    s.users_file.write_text(json.dumps({"telegram:1": {"drive": "alice"}, "telegram:2": {"drive": "ghost"}, "telegram:3": {}, "telegram:4": {"mail": "default"}}))
    gw = Gateway.__new__(Gateway); gw.s = s; gw.reg = REG
    assert [gw.user_drive(f"telegram:{i}") for i in (1, 2, 3, 4)] == ["alice", None, None, None]      # an unknown account name, no entry, and "no Drive" all mean no Drive
    assert gw._uses_drive(REG.intents["drive_search"]) and not gw._uses_drive(REG.intents["mail_read"]) and not gw._uses_drive(REG.intents["document_read"])
    assert "drive-u-alice" in gw.expected_servers()


def test_a_file_search_never_goes_to_gmail():
    assert drive_not_mail("Summarize the new files in my Drive", ["mail_read"]) == ["drive_search"]
    assert drive_not_mail("Find the file called lease", ["mail_manage"]) == ["drive_search"]
    assert drive_not_mail("Summarize my emails this week", ["mail_read"]) == ["mail_read"]            # email words keep the mail intent
    assert drive_not_mail("What's in the budget spreadsheet in Drive and any email about it?", ["mail_read"]) == ["drive_search", "mail_read"]
    assert drive_not_mail("Turn off the fans", ["home_control"]) == ["home_control"]
    assert drive_not_mail("hello", []) == []


def test_an_attached_file_still_wins_over_drive():
    att = "\n\n[Attached document: /x/inbox/docs/a.pdf]"
    assert drive_not_mail("Summarize this" + att, ["drive_search"]) == ["drive_search"]                  # the Drive rule does not look at attachments; the attachment rule runs after it
    assert document_not_mail("Summarize this" + att, ["drive_search"]) == ["document_read", "drive_search"]


def test_eval_set_covers_drive_and_keeps_email_summaries_on_gmail():
    items = [json.loads(l) for l in (ROOT / "eval/eval_set.jsonl").read_text().splitlines()]
    drive = [i for i in items if "drive_search" in i["expected_intents"]]
    assert len(drive) >= 8
    assert any(i["expected_intents"] == ["mail_read"] and "summar" in i["text"].lower() for i in items)
