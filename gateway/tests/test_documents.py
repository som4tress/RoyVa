"""Reading attached documents: the skill exists, is read-only and has no mail tools, and a request about an attached file never lands on Gmail."""
import json
from pathlib import Path

from royva_gateway import registry
from royva_gateway.router import document_not_mail

ROOT = Path(__file__).resolve().parent.parent
REG = registry.load(ROOT / "registry")
ATT = "\n\n[Attached document: /home/u/RoyVa/runtime/data/inbox/docs/2026-11-22-ab12-lease.pdf]"


def test_the_skill_is_active_read_only_and_has_no_mail_or_write_tools():
    i = REG.intents["document_read"]
    assert i.status == "active" and i.profile.write_policy == "read_only"
    assert set(i.profile.tools) == {"docs.read_document", "docs.find_in_document"}
    assert not i.profile.scope                       # every household member may read the files they send
    assert not any(t.startswith(("gmail", "machine", "ha")) for t in i.profile.tools)


def test_the_tools_are_in_the_catalog_as_read_only():
    for tid, action in (("docs.read_document", "docs_read_document"), ("docs.find_in_document", "docs_find_in_document")):
        t = REG.tools[tid]; assert t.action == action and t.risk == "read" and t.server == "docs" and t.available


def test_the_skill_has_examples_and_negatives_that_keep_mail_apart():
    i = REG.intents["document_read"]
    assert len(i.examples) >= 8 and any("summar" in e.lower() for e in i.examples) and any("pdf" in e.lower() for e in i.examples)
    assert any("email" in n.lower() for n in i.negatives)                    # "summarize my unread emails" is a mail request, said so in the skill
    for mail in ("mail_read", "mail_manage"):
        text = " ".join(REG.intents[mail].negatives).lower()
        assert "pdf" in text or "document" in text or "attached" in text, mail   # and the mail skills say that a file is not theirs


def test_a_file_attached_to_a_summarize_request_goes_to_the_reader_not_gmail():
    assert document_not_mail("Summarize this" + ATT, ["mail_read"]) == ["document_read"]
    assert document_not_mail("Summarize this" + ATT, ["mail_manage"]) == ["document_read"]
    assert document_not_mail("What is the notice period?" + ATT, []) == ["document_read"]
    assert document_not_mail("Summarize this" + ATT, ["document_read"]) == ["document_read"]


def test_other_intents_in_the_same_message_are_kept_and_the_reader_comes_first():
    assert document_not_mail("Summarize this and what's the weather" + ATT, ["web_lookup"]) == ["document_read", "web_lookup"]


def test_a_message_that_really_is_about_email_keeps_its_mail_intent():
    assert document_not_mail("Check my Gmail for anything about this contract" + ATT, ["mail_read"]) == ["document_read", "mail_read"]
    assert document_not_mail("Did the landlord email me back?" + ATT, ["mail_read"]) == ["document_read", "mail_read"]


def test_without_an_attachment_nothing_changes():
    for text, intents in (("Summarize my unread emails", ["mail_read"]), ("Turn off the fans", ["home_control"]), ("What is this PDF about", ["mail_read"]), ("hello", [])):
        assert document_not_mail(text, intents) == intents


def test_a_photo_attachment_is_not_a_document():
    assert document_not_mail("Make this look like a painting\n\n[Attached photo: /x/inbox/a.jpg]", ["image_set"]) == ["image_set"]


def test_eval_set_covers_documents_and_the_summarize_split():
    items = [json.loads(l) for l in (ROOT / "eval/eval_set.jsonl").read_text().splitlines()]
    doc = [i for i in items if "document_read" in i["expected_intents"]]
    assert len(doc) >= 6
    assert any(i["expected_intents"] == ["mail_read"] and "summar" in i["text"].lower() for i in items)      # the neighbour that must stay on Gmail
    assert any("[Attached document" in i["text"] for i in doc)
