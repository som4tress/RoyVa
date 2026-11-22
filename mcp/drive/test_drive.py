"""Tests for the Google Drive reader MCP (mcp/drive): safe queries, listing, reading native and uploaded files, read-only behaviour. Google is a fake.
Run with the gateway's python (it holds the document libraries):  gateway/.venv/bin/python -m unittest mcp.drive.test_drive"""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "docs"))
import server  # noqa: E402

GDOC, GSHEET, GSLIDES, GFOLDER = ("application/vnd.google-apps.document", "application/vnd.google-apps.spreadsheet",
                                  "application/vnd.google-apps.presentation", "application/vnd.google-apps.folder")
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class FakeGoogle:
    """Answers the few Drive calls the server makes and records every request."""
    def __init__(self):
        self.calls, self.files, self.bodies, self.list_result = [], {}, {}, None

    def __call__(self, method, url, token, data=None, headers=None, raw=False):
        self.calls.append((method, url, token))
        u = urlparse(url); q = parse_qs(u.query)
        if u.path.endswith("/token"):
            return {"access_token": "at-1", "expires_in": 3600}
        if u.path == "/drive/v3/files":
            return self.list_result if self.list_result is not None else {"files": list(self.files.values())}
        fid = u.path.split("/")[4]
        if fid not in self.files:
            raise server.DriveError("File not found.")
        if u.path.endswith("/export"):
            return self.bodies[(fid, q["mimeType"][0])]
        if q.get("alt") == ["media"]:
            return self.bodies[(fid, "media")]
        return self.files[fid]

    def last_list(self):
        return parse_qs(urlparse([c for c in self.calls if urlparse(c[1]).path == "/drive/v3/files"][-1][1]).query)


def f(fid, name, mime="text/plain", modified="2026-11-20T10:00:00.000Z", size="100", **extra):
    return {"id": fid, "name": name, "mimeType": mime, "modifiedTime": modified, "size": size, "webViewLink": f"https://drive.google.com/file/d/{fid}/view"} | extra


def make_docx(text):
    import docx
    b = io.BytesIO(); d = docx.Document(); d.add_paragraph(text); d.save(b); return b.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.g = FakeGoogle()
        d = Path(tempfile.mkdtemp())
        (d / "keys.json").write_text(json.dumps({"web": {"client_id": "cid", "client_secret": "sek", "token_uri": "https://oauth2.googleapis.com/token"}}))
        (d / "cred.json").write_text(json.dumps({"refresh_token": "rt-1", "access_token": "old"}))
        os.environ["DRIVE_OAUTH_KEYS_PATH"], os.environ["DRIVE_CREDENTIALS_PATH"] = str(d / "keys.json"), str(d / "cred.json")
        self.d = server.Drive(http=self.g)

    def tearDown(self):
        for k in ("DRIVE_OAUTH_KEYS_PATH", "DRIVE_CREDENTIALS_PATH"):
            os.environ.pop(k, None)


class SearchTests(Base):
    def test_the_token_is_refreshed_once_and_sent_with_every_call(self):
        self.d.search_files(query="lease"); self.d.search_files(query="rent")
        self.assertEqual(len([c for c in self.g.calls if c[1].endswith("/token")]), 1)
        self.assertTrue(all(c[2] in (None, "at-1") for c in self.g.calls))

    def test_quotes_and_backslashes_in_what_the_model_asks_cannot_break_out_of_the_query(self):
        self.d.search_files(query="it's a \\ test' or name contains '")
        q = self.g.last_list()["q"][0]
        self.assertIn("fullText contains 'it\\'s a \\\\ test\\' or name contains \\''", q)
        self.assertTrue(q.startswith("trashed = false"))

    def test_name_type_dates_and_folder_become_conditions(self):
        self.d.search_files(name="Lease", type="pdf", modified_after="2026-11-15", modified_before="2026-11-22T10:00:00", folder_id="1AbC_-x")
        q = self.g.last_list()["q"][0]
        for part in ("name contains 'Lease'", "mimeType = 'application/pdf'", "modifiedTime > '2026-11-15T00:00:00'", "modifiedTime < '2026-11-22T10:00:00'", "'1AbC_-x' in parents"):
            self.assertIn(part, q)

    def test_type_words_map_to_google_types(self):
        for word, mime in (("document", GDOC), ("spreadsheet", GSHEET), ("presentation", GSLIDES), ("folder", GFOLDER)):
            self.d.search_files(type=word); self.assertIn(f"mimeType = '{mime}'", self.g.last_list()["q"][0])
        self.assertIn("mimeType contains 'image/'", (self.d.search_files(type="image"), self.g.last_list()["q"][0])[1])
        self.assertFalse(self.d.search_files(type="rocket")["ok"])

    def test_bad_dates_and_ids_are_refused_before_anything_is_sent(self):
        n = len(self.g.calls)
        for bad in ({"modified_after": "last tuesday"}, {"modified_after": "2026-13-45"}, {"folder_id": "x' in parents or '1"}, {"folder_id": "../etc"}):
            r = self.d.search_files(**bad); self.assertFalse(r["ok"], bad); self.assertTrue(r["error"])
        self.assertEqual(len(self.g.calls), n)

    def test_results_are_newest_first_limited_and_ask_for_few_fields(self):
        self.d.search_files(query="x", limit=500)
        q = self.g.last_list()
        self.assertEqual(q["orderBy"], ["modifiedTime desc"]); self.assertLessEqual(int(q["pageSize"][0]), 50)
        self.assertEqual(q["supportsAllDrives"], ["true"]); self.assertEqual(q["includeItemsFromAllDrives"], ["true"])
        fields = q["fields"][0]
        self.assertIn("files(", fields); self.assertNotIn("permissions", fields); self.assertNotIn("owners", fields)

    def test_each_result_says_what_it_is(self):
        self.g.files = {"1": f("1", "Budget", GSHEET), "2": f("2", "Lease.pdf", "application/pdf", size="2048"), "3": f("3", "Notes", GDOC), "4": f("4", "Taxes", GFOLDER, size=None)}
        r = self.d.search_files(query="")
        self.assertTrue(r["ok"]); kinds = {x["name"]: x["kind"] for x in r["files"]}
        self.assertEqual(kinds, {"Budget": "spreadsheet", "Lease.pdf": "pdf", "Notes": "document", "Taxes": "folder"})
        self.assertEqual(r["files"][1]["id"], "2"); self.assertIn("modified", r["files"][1]); self.assertIn("link", r["files"][1])
        self.assertIn("notice", r)

    def test_a_listing_names_the_folder_and_starts_at_the_root_by_default(self):
        self.d.list_folder()
        self.assertIn("'root' in parents", self.g.last_list()["q"][0])
        self.d.list_folder(folder_id="1AbC")
        self.assertIn("'1AbC' in parents", self.g.last_list()["q"][0])


class ReadTests(Base):
    def test_a_google_doc_is_exported_as_text_and_read_in_pieces(self):
        self.g.files["d1"] = f("d1", "Plan", GDOC); self.g.bodies[("d1", "text/plain")] = "Intro. " + "word " * 3000 + "The deadline is Friday."
        a = self.d.read_file("d1", 0, 2000)
        self.assertTrue(a["ok"]); self.assertEqual(a["name"], "Plan"); self.assertLessEqual(len(a["text"]), 2000); self.assertEqual(a["next_start"], len(a["text"]))
        self.assertIn("Untrusted", a["notice"])
        last = self.d.read_file("d1", a["total_chars"] - 5, 2000)
        self.assertIsNone(last["next_start"])

    def test_a_google_sheet_is_exported_as_csv_and_slides_as_text(self):
        self.g.files["s1"] = f("s1", "Budget", GSHEET); self.g.bodies[("s1", "text/csv")] = "Item,Cost\nRent,1200\n"
        self.assertIn("Rent,1200", self.d.read_file("s1")["text"])
        self.g.files["p1"] = f("p1", "Deck", GSLIDES); self.g.bodies[("p1", "text/plain")] = "Roadmap"
        self.assertIn("Roadmap", self.d.read_file("p1")["text"])

    def test_an_uploaded_word_file_is_downloaded_and_read_with_the_document_reader(self):
        self.g.files["w1"] = f("w1", "Agreement.docx", DOCX, size="9000"); self.g.bodies[("w1", "media")] = make_docx("The notice period is 30 days.")
        r = self.d.read_file("w1")
        self.assertTrue(r["ok"], r); self.assertIn("notice period is 30 days", r["text"])
        self.assertTrue(any("alt=media" in c[1] for c in self.g.calls))

    def test_nothing_is_left_on_disk_after_reading(self):
        before = set(Path(tempfile.gettempdir()).iterdir())
        self.g.files["w1"] = f("w1", "A.docx", DOCX); self.g.bodies[("w1", "media")] = make_docx("secret words")
        self.d.read_file("w1")
        self.assertEqual({p for p in set(Path(tempfile.gettempdir()).iterdir()) - before if "drive" in p.name.lower()}, set())

    def test_folders_big_files_and_unreadable_types_are_clear_errors(self):
        self.g.files["f1"] = f("f1", "Taxes", GFOLDER); self.g.files["b1"] = f("b1", "Big.pdf", "application/pdf", size=str(200 * 1024 * 1024))
        self.g.files["v1"] = f("v1", "Movie.mp4", "video/mp4", size="1000"); self.g.files["o1"] = f("o1", "Old.doc", "application/msword", size="1000")
        for fid, word in (("f1", "folder"), ("b1", "too large"), ("v1", "cannot be read"), ("o1", ".docx")):
            r = self.d.read_file(fid); self.assertFalse(r["ok"], fid); self.assertIn(word, r["error"].lower(), fid)
        self.assertFalse(any("alt=media" in c[1] for c in self.g.calls))                    # a big or unreadable file is never downloaded

    def test_a_missing_file_and_a_bad_id_are_errors_not_crashes(self):
        self.assertIn("not found", self.d.read_file("nope")["error"].lower())
        for bad in ("../x", "a b", "x/y", "", "x?alt=media"):
            self.assertFalse(self.d.read_file(bad)["ok"], bad)

    def test_find_in_file_returns_hits_with_context(self):
        self.g.files["d1"] = f("d1", "Plan", GDOC); self.g.bodies[("d1", "text/plain")] = "x " * 500 + "the security deposit is two months" + " y" * 500
        r = self.d.find_in_file("d1", "Security Deposit", 40)
        self.assertTrue(r["ok"]); self.assertEqual(len(r["hits"]), 1); self.assertIn("deposit is two months", r["hits"][0]["context"])

    def test_the_same_file_is_not_exported_twice_while_unchanged(self):
        self.g.files["d1"] = f("d1", "Plan", GDOC); self.g.bodies[("d1", "text/plain")] = "hello there"
        self.d.read_file("d1"); self.d.read_file("d1", 3); self.d.find_in_file("d1", "hello")
        self.assertEqual(len([c for c in self.g.calls if "/export" in c[1]]), 1)
        self.g.files["d1"] = f("d1", "Plan", GDOC, modified="2026-11-21T10:00:00.000Z"); self.g.bodies[("d1", "text/plain")] = "changed text"
        self.assertIn("changed text", self.d.read_file("d1")["text"])


class SafetyTests(Base):
    def test_only_the_four_read_tools_exist(self):
        names = {t["name"] for t in server.TOOLS}
        self.assertEqual(names, {"search_files", "list_folder", "read_file", "find_in_file"})
        self.assertTrue(all(t["description"] and t["inputSchema"] for t in server.TOOLS))

    def test_nothing_but_reads_ever_goes_to_google(self):
        self.g.files["d1"] = f("d1", "Plan", GDOC); self.g.bodies[("d1", "text/plain")] = "x"
        self.d.search_files(query="a"); self.d.list_folder(); self.d.read_file("d1"); self.d.find_in_file("d1", "x")
        for method, url, token in self.g.calls:
            self.assertEqual(method, "POST" if url.endswith("/token") else "GET", url)
            self.assertNotRegex(url, r"permissions|trash|copy|/watch|delete")

    def test_json_rpc_lists_and_calls_the_tools_and_marks_errors(self):
        server.CLIENT = self.d
        tools = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
        self.assertEqual(len(tools), 4)
        ok = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "search_files", "arguments": {"query": "lease"}}})
        self.assertFalse(ok["result"]["isError"]); self.assertTrue(json.loads(ok["result"]["content"][0]["text"])["ok"])
        bad = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "read_file", "arguments": {"file_id": "../x"}}})
        self.assertTrue(bad["result"]["isError"])

    def test_google_errors_come_back_as_plain_messages(self):
        def boom(*a, **k):
            raise server.DriveError("Google refused the request (403): the Drive API has not been enabled.")
        d = server.Drive(http=boom)
        r = d.search_files(query="x")
        self.assertFalse(r["ok"]); self.assertIn("403", r["error"])


if __name__ == "__main__":
    unittest.main()
