"""Bulk Gmail tidy server: paging, chunked batchModify, safety limits, dry-run. A fake Gmail stands in for the network."""
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

SPEC = importlib.util.spec_from_file_location("gmail_tidy", Path(__file__).resolve().parents[2] / "mcp" / "mail" / "gmail_tidy.py")
gt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gt)


class FakeGmail(gt.Gmail):
    def __init__(self, total=1200):
        self.total, self.calls, self.queries = total, [], []
        super().__init__(http=self.http)
        self._tok, self._exp = "t", 10**12

    def http(self, method, url, token, body=None, headers=None):
        u = urlparse(url); q = parse_qs(u.query)
        if method == "GET" and u.path.endswith("/messages"):
            self.queries.append(q["q"][0])
            start = int(q.get("pageToken", ["0"])[0]); n = int(q["maxResults"][0])
            ids = [{"id": f"m{i}"} for i in range(start, min(start + n, self.total))]
            nxt = start + n
            return {"messages": ids, **({"nextPageToken": str(nxt)} if nxt < self.total else {})}
        if method == "GET" and "/messages/m" in u.path:
            return {"payload": {"headers": [{"name": "From", "value": "Nextdoor <x@nextdoor.com>"}, {"name": "Subject", "value": "Digest"}, {"name": "Date", "value": "Mon"}]}}
        if method == "POST" and u.path.endswith("/batchModify"):
            self.calls.append(json.loads(body)); return {}
        raise AssertionError((method, url))


def test_count_pages_and_samples_without_changing_anything():
    gm = FakeGmail(1200)
    out = gt.count_matching({"query": "from:nextdoor.com"}, gm)
    assert out["count"] == 1200 and out["at_least"] is False and len(out["examples"]) == 5 and gm.calls == []


def test_trash_pages_everything_and_batches_in_chunks_of_1000():
    gm = FakeGmail(1200)
    out = gt.tidy_matching({"query": "from:nextdoor.com", "action": "trash"}, gm)
    assert out["changed"] == 1200 and out["remaining"] is False and "Moved to Trash 1200" in out["did"]
    assert [len(c["ids"]) for c in gm.calls] == [1000, 200]
    assert all(c["addLabelIds"] == ["TRASH"] for c in gm.calls)
    assert gm.queries[0].endswith("-in:trash")                                   # never re-trashes what is already in Trash


def test_limit_caps_one_call_and_says_more_remain():
    gm = FakeGmail(3000)
    out = gt.tidy_matching({"query": "from:a.com", "action": "trash", "limit": 1000}, gm)
    assert out["changed"] == 1000 and out["remaining"] is True and "run it again" in out["did"]


def test_too_broad_queries_are_refused_and_nothing_is_changed():
    gm = FakeGmail()
    for q in ["", "  ", "in:inbox", "*", "is:unread", "x"]:
        assert gt.tidy_matching({"query": q, "action": "trash"}, gm)["ok"] is False
    assert gm.calls == []


def test_there_is_no_permanent_delete_or_send_path():
    src = Path(gt.__file__).read_text()
    assert "batchDelete" not in src and "/send" not in src and "messages.delete" not in src.lower()
    assert set(gt.ACTIONS) == {"trash", "archive", "mark_read", "mark_unread"}


def test_unknown_action_is_rejected():
    assert gt.tidy_matching({"query": "from:a.com", "action": "delete_forever"}, FakeGmail())["ok"] is False


def test_dry_run_reports_without_acting(monkeypatch, tmp_path):
    monkeypatch.setattr(gt, "DRY_FLAG", tmp_path / "dry_run"); (tmp_path / "dry_run").write_text("")
    gm = FakeGmail(50)
    out = gt.tidy_matching({"query": "from:a.com", "action": "trash"}, gm)
    assert out["dry_run"] is True and out["would_change"] == 50 and gm.calls == [] and "[DRY RUN" in out["did"]


def test_archive_and_mark_read_use_the_right_labels():
    gm = FakeGmail(10)
    gt.tidy_matching({"query": "from:a.com", "action": "archive"}, gm)
    gt.tidy_matching({"query": "from:a.com", "action": "mark_read"}, gm)
    assert gm.calls[0] == {"ids": [f"m{i}" for i in range(10)], "removeLabelIds": ["INBOX"]}
    assert gm.calls[1]["removeLabelIds"] == ["UNREAD"]


def test_mcp_protocol_lists_the_tools(capsys):
    gt.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in json.loads(capsys.readouterr().out)["result"]["tools"]]
    assert names == ["count_matching", "tidy_ids", "tidy_matching"]


def test_several_bare_senders_become_one_or_group():
    n = gt.normalize_query
    assert n("from:a@x.com from:b@y.com older_than:1y") == "{from:a@x.com from:b@y.com} older_than:1y"
    assert n('from:"A B" from:c@d.com') == '{from:"A B" from:c@d.com}'
    assert n("from:a@x.com") == "from:a@x.com"                       # single sender untouched
    assert n("{from:a from:b} is:unread") == "{from:a from:b} is:unread"  # already grouped
    assert n("from:a -from:b") == "from:a -from:b"                   # negation is not an OR candidate


def test_trash_with_space_joined_senders_uses_one_query():
    g = FakeGmail(total=3)
    gt.tidy_matching({"query": "from:a@x.com from:b@y.com", "action": "trash"}, gm=g)
    assert g.queries[0].startswith("{from:a@x.com from:b@y.com}")
    assert len(g.calls) == 1


def test_tidy_ids_changes_exactly_the_given_messages_in_one_call():
    gm = FakeGmail(5)
    out = gt.tidy_ids({"ids": ["1a1b99fec67dd672", "1a1b97b7dadfffcf", "1a1b99fec67dd672"], "action": "trash"}, gm)
    assert out["changed"] == 2 and len(gm.calls) == 1 and gm.calls[0]["addLabelIds"] == ["TRASH"] and gm.calls[0]["ids"] == ["1a1b99fec67dd672", "1a1b97b7dadfffcf"]


def test_tidy_ids_rejects_junk_ids_and_empty_lists():
    gm = FakeGmail(5)
    for bad in ([], ["not an id"], ["abc"], "1a1b99fec67dd672", [123]):
        assert gt.tidy_ids({"ids": bad, "action": "trash"}, gm)["ok"] is False
    assert gm.calls == []


def test_count_is_exact_above_the_old_5000_cap_and_flags_when_it_is_only_a_lower_bound():
    g = FakeGmail(total=6200)
    r = gt.count_matching({"query": "is:unread"}, gm=g)
    assert r["count"] == 6200 and r["at_least"] is False and not g.calls            # exact, and counting changes nothing
    big = FakeGmail(total=gt.COUNT_CAP + 10)
    r = gt.count_matching({"query": "is:unread"}, gm=big)
    assert r["count"] == gt.COUNT_CAP and r["at_least"] is True
