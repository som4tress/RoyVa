"""Protocol-level tests for the img_video MCP wrapper and its detached runner: the server runs as a subprocess, a stub stands in for the agent (no GPU, no web)."""
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SERVER = Path(__file__).with_name("server.py")
STUB = '''
import json, sys, pathlib, os, time
mode = os.environ.get("STUB_MODE", "ok"); d = pathlib.Path(os.environ["STUB_DIR"]); pathlib.Path(os.environ["STUB_DIR"], "progress_env.txt").write_text(os.environ.get("IMG_VIDEO_PROGRESS_FILE", "NONE")); time.sleep(float(os.environ.get("STUB_SLEEP", "0")))
if mode == "fail": print(json.dumps({"ok": False, "job": "j1", "error": "ComfyUI is not reachable"})); sys.exit(2)
if mode == "garbage": print("no json here"); sys.exit(1)
imgs = []
for i in (1, 2, 3):
    f = d / f"src{i}.png"; f.write_bytes(b"\\x89PNG" + bytes(100)); imgs.append({"index": i, "path": str(f), "topic": f"topic {i}", "caption": f"caption {i}"})
out = {"ok": True, "job": "20261116-test", "title": "Test set", "images": imgs, "stage_seconds": {"images": 30.0}, "args_seen": sys.argv[1:]}
if "--video" in sys.argv:
    v = d / "src.mp4"; v.write_bytes(bytes(2000)); out["video"] = {"path": str(v), "seconds": 6.0, "mb": 0.1, "title": "Test video"}
print(json.dumps(out))
'''
IMAGE_STUB = '''
import json, sys, pathlib, os
d = pathlib.Path(os.environ["STUB_DIR"]); f = d / "single.png"; f.write_bytes(b"\\x89PNG" + bytes(50)); text = sys.stdin.read()
if os.environ.get("STUB_MODE") == "fail": print(json.dumps({"ok": False, "error": "no GPU anywhere"})); sys.exit(2)
print(json.dumps({"ok": True, "job": "s1", "image_path": str(f), "prompt_used": text[:20], "original_chars": len(text), "chars": min(len(text), 500), "method": "rewrite" if len(text) > 500 else "none",
                  "backend": "3090", "secs": 14.4, "seed": 7, "width": 1024, "height": 1024, "note": ""}))
'''


os.environ.setdefault("ROYVA_MCP_CANCEL_LOG", str(Path(tempfile.gettempdir()) / "royva_test_mcp_cancel.log"))        # tests never write the real runtime log


class Server:
    def __init__(self, tmp, mode="ok", dry=False, sleep="0", bg="async"):        # bg: "async" | "sync" | "flag" (decided per call by the flag file, like production)
        (tmp / "stub.py").write_text(STUB); (tmp / "image_stub.py").write_text(IMAGE_STUB)
        env = dict(os.environ, ROYVA_IMAGE_DIR=str(tmp / "images"), ROYVA_OUTBOX_DIR=str(tmp / "outbox"), ROYVA_VIDEO_DIR=str(tmp / "videos"), ROYVA_IMGVIDEO_LOCK=str(tmp / "lock"),
                   ROYVA_INBOX_DIR=str(tmp / "inbox"), ROYVA_OPENCODE_DB=str(tmp / "opencode.db"), ROYVA_DRY_RUN_FLAG=str(tmp / "no_such_flag"), ROYVA_IMGVIDEO_ASYNC_FLAG=str(tmp / "async_flag"), ROYVA_IMGVIDEO_CMD=json.dumps([sys.executable, str(tmp / "stub.py")]),
                   ROYVA_IMGVIDEO_IMAGE_CMD=json.dumps([sys.executable, str(tmp / "image_stub.py")]), STUB_MODE=mode, STUB_DIR=str(tmp), STUB_SLEEP=sleep, ROYVA_DRY_RUN="1" if dry else "0")
        env.pop("ROYVA_IMGVIDEO_ASYNC", None)
        if bg in ("async", "sync"): env["ROYVA_IMGVIDEO_ASYNC"] = "1" if bg == "async" else "0"
        self.p = subprocess.Popen([sys.executable, str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env); self.tmp = tmp

    def rpc(self, method, params=None, ident=1):
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}}) + "\n"); self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())

    def call(self, args, tool="generate_image_set"):
        r = self.rpc("tools/call", {"name": tool, "arguments": args})["result"]
        return [json.loads(c["text"]) for c in r["content"]], r.get("isError", False)

    def done(self, job, timeout=15):
        f = self.tmp / "outbox" / "done" / f"{job}.json"; t0 = time.time()
        while time.time() - t0 < timeout:
            if f.exists(): return json.loads(f.read_text())
            time.sleep(0.1)
        raise AssertionError(f"no outbox file for {job}")

    def close(self): self.p.stdin.close(); self.p.wait(timeout=10)


class T(unittest.TestCase):
    def setUp(self): self.tmp = Path(tempfile.mkdtemp())

    def test_initialize_and_tool_list(self):
        s = Server(self.tmp)
        self.assertEqual(s.rpc("initialize", {"protocolVersion": "2025-03-26"})["result"]["serverInfo"]["name"], "img-video")
        tools = {t["name"]: t for t in s.rpc("tools/list")["result"]["tools"]}
        self.assertEqual(set(tools), {"generate_image", "generate_image_set", "generate_video"})
        self.assertEqual(tools["generate_image"]["inputSchema"]["required"], ["prompt"]); self.assertEqual(tools["generate_video"]["inputSchema"]["required"], ["query"])
        self.assertIn("RETURNS AT ONCE", tools["generate_image_set"]["description"]); self.assertIn("RETURNS AT ONCE", tools["generate_video"]["description"]); s.close()

    def test_validation(self):
        s = Server(self.tmp)
        for tool in ("generate_image_set", "generate_video"):
            for bad in ({}, {"query": "  "}, {"query": "x" * 1001}, {"query": "ok", "count": 0}, {"query": "ok", "count": 99}, {"query": "ok", "aspect": "4:3"}):
                parts, _ = s.call(bad, tool); self.assertFalse(parts[0]["ok"], (tool, bad))
        for bad in ({}, {"prompt": " "}, {"prompt": "x" * 6001}, {"prompt": "a", "width": 1000}, {"prompt": "a", "height": 64}):
            parts, _ = s.call(bad, "generate_image"); self.assertFalse(parts[0]["ok"] if isinstance(parts[0], dict) else parts["ok"], bad)
        s.close()

    def test_dry_run_does_nothing(self):
        s = Server(self.tmp, dry=True)
        for tool, args in (("generate_image_set", {"query": "10 pictures of cats"}), ("generate_video", {"query": "a dog running"}), ("generate_image", {"prompt": "a cat"})):
            parts, _ = s.call(args, tool); self.assertTrue(parts[0]["ok"]); self.assertIn("DRY RUN", parts[0]["did"])
        self.assertFalse((self.tmp / "outbox").exists()); self.assertFalse((self.tmp / "images").exists()); s.close()

    def test_a_set_returns_at_once_and_the_pictures_arrive_in_the_outbox(self):
        s = Server(self.tmp, sleep="1"); t0 = time.time()
        parts, err = s.call({"query": "three pictures about rain", "count": 3, "aspect": "16:9"})
        self.assertLess(time.time() - t0, 0.9); self.assertFalse(err)                                    # it did not wait for the 1 s agent
        self.assertEqual(len(parts), 1); r = parts[0]; self.assertTrue(r["ok"] and r["async_job"] and r["kind"] == "set" and "image_path" not in r); self.assertIn("posted to this chat", r["did"])
        done = s.done(r["async_job"]); self.assertTrue(done["ok"]); self.assertEqual(done["kind"], "images"); self.assertEqual([i["index"] for i in done["images"]], [1, 2, 3])
        for im in done["images"]:
            f = Path(im["path"]); self.assertTrue(f.is_file()); self.assertEqual(f.parent, self.tmp / "images"); self.assertTrue(f.name.startswith("imgset-20261116-test-"))
        self.assertEqual(done["images"][1]["caption"], "caption 2"); s.close()

    def test_a_video_job_leaves_a_video_and_asks_the_agent_for_one(self):
        s = Server(self.tmp); parts, _ = s.call({"query": "how rainbows form"}, "generate_video"); r = parts[0]
        self.assertTrue(r["ok"] and r["kind"] == "video"); done = s.done(r["async_job"])
        self.assertTrue(done["ok"] and done["kind"] == "video"); f = Path(done["video"]["path"]); self.assertTrue(f.is_file()); self.assertEqual(f.parent, self.tmp / "videos"); self.assertEqual(done["title"], "Test video"); s.close()

    def test_research_text_reaches_the_agent_as_a_file_and_the_query_limit_is_unchanged(self):
        s = Server(self.tmp); facts = "Fact: X happened. " * 20
        parts, _ = s.call({"query": "satirical news video", "research_text": facts}, "generate_video"); job = parts[0]["async_job"]; self.assertTrue(s.done(job)["ok"])
        f = self.tmp / "outbox" / "logs" / f"{job}.research.txt"; self.assertEqual(f.read_text(), facts.strip())
        parts, _ = s.call({"query": "x" * 1001, "research_text": facts}, "generate_video"); self.assertFalse(parts[0]["ok"]); self.assertIn("too long", parts[0]["error"]); s.close()

    def agent_args(self, job):
        out = (self.tmp / "outbox" / "logs" / f"{job}.agent.out").read_text().strip().splitlines()[-1]; return json.loads(out)["args_seen"]

    def test_reference_photos_from_the_inbox_reach_the_agent_and_nothing_else_does(self):
        inbox = self.tmp / "inbox"; inbox.mkdir(); a, b = inbox / "a.jpg", inbox / "b.PNG"; a.write_bytes(b"x"); b.write_bytes(b"x"); (self.tmp / "outside.jpg").write_bytes(b"x"); (inbox / "note.txt").write_text("x")
        s = Server(self.tmp)
        parts, _ = s.call({"query": "me in Paris", "reference_photos": [str(a), str(b)]}, "generate_video"); job = parts[0]["async_job"]; s.done(job)
        args = self.agent_args(job); self.assertEqual([args[i + 1] for i, x in enumerate(args) if x == "--reference"], [str(a.resolve()), str(b.resolve())])
        parts, _ = s.call({"query": "me in Paris", "reference_photos": [str(a)]}, "generate_image_set"); s.done(parts[0]["async_job"]); self.assertIn("--reference", self.agent_args(parts[0]["async_job"]))         # sets too
        for bad in (self.tmp / "outside.jpg", inbox / "note.txt", inbox / "missing.jpg", inbox / ".." / "outside.jpg", "/etc/passwd"):
            parts, err = s.call({"query": "me in Paris", "reference_photos": [str(bad)]}, "generate_video"); self.assertFalse(parts[0]["ok"], bad); self.assertIn("not one of the photos", parts[0]["error"])
        parts, _ = s.call({"query": "no photo"}, "generate_video"); job = parts[0]["async_job"]; s.done(job); self.assertNotIn("--reference", self.agent_args(job))      # without photos nothing changes
        many = []
        for k in range(8): f = inbox / f"p{k}.jpg"; f.write_bytes(b"x"); many.append(str(f))
        parts, _ = s.call({"query": "me", "reference_photos": many}, "generate_video"); job = parts[0]["async_job"]; s.done(job); self.assertEqual(self.agent_args(job).count("--reference"), 6)          # six at most
        parts, _ = s.call({"query": "the couple", "reference_photos": [{"path": str(a), "who": "my husband"}, {"path": str(b), "who": "me | wife"}, str(inbox / "p0.jpg")]}, "generate_video"); job = parts[0]["async_job"]; s.done(job)
        args = self.agent_args(job); self.assertEqual([args[i + 1] for i, x in enumerate(args) if x == "--reference"], [f"{a.resolve()}|my husband", f"{b.resolve()}|me   wife", str((inbox / 'p0.jpg').resolve())])      # the label rides along, a '|' in it cannot break the format
        parts, err = s.call({"query": "x", "reference_photos": [{"path": str(self.tmp / "outside.jpg"), "who": "me"}]}, "generate_video"); self.assertFalse(parts[0]["ok"]); s.close()                         # labels do not bypass the inbox rule

    def test_photos_of_the_same_album_the_chat_model_left_out_are_added_in_the_order_they_were_sent(self):
        inbox = self.tmp / "inbox"; (inbox / ".albums").mkdir(parents=True)
        a, b, c, d = (inbox / f"{n}.jpg" for n in "abcd")
        for f in (a, b, c, d): f.write_bytes(b"x")
        (inbox / ".albums" / "one.json").write_text(json.dumps({"files": ["a.jpg", "b.jpg", "c.jpg"]})); (inbox / ".albums" / "bad.json").write_text("not json")
        s = Server(self.tmp)
        parts, _ = s.call({"query": "us in Paris", "reference_photos": [{"path": str(b), "who": "my wife"}, str(a)]}, "generate_video"); job = parts[0]["async_job"]; s.done(job)       # the model passed 2 of the 3 photos, in another order
        args = self.agent_args(job); got = [args[i + 1] for i, x in enumerate(args) if x == "--reference"]
        self.assertEqual(got, [str(a.resolve()), f"{b.resolve()}|my wife", str(c.resolve())])                                   # all three, in the order sent, the label kept
        parts, _ = s.call({"query": "just this", "reference_photos": [str(d)]}, "generate_video"); job = parts[0]["async_job"]; s.done(job)
        args = self.agent_args(job); self.assertEqual([args[i + 1] for i, x in enumerate(args) if x == "--reference"], [str(d.resolve())]); s.close()           # a photo from another message stays alone

    def test_the_tools_offer_reference_photos_as_an_optional_list(self):
        s = Server(self.tmp); tools = {t["name"]: t for t in s.rpc("tools/list")["result"]["tools"]}
        for name in ("generate_video", "generate_image_set"):
            prop = tools[name]["inputSchema"]["properties"]["reference_photos"]; self.assertEqual((prop["type"], prop["maxItems"]), ("array", 6)); self.assertNotIn("reference_photos", tools[name]["inputSchema"]["required"])
        self.assertNotIn("reference_photos", tools["generate_image"]["inputSchema"]["properties"]); s.close()

    def test_research_text_is_clipped_not_rejected_and_is_optional(self):
        s = Server(self.tmp); parts, _ = s.call({"query": "news video", "research_text": "a" * 9000}, "generate_video"); job = parts[0]["async_job"]; self.assertTrue(parts[0]["ok"]); s.done(job)
        self.assertEqual(len((self.tmp / "outbox" / "logs" / f"{job}.research.txt").read_text()), 6000)
        parts, _ = s.call({"query": "a dog clip"}, "generate_video"); job = parts[0]["async_job"]; s.done(job)
        self.assertFalse((self.tmp / "outbox" / "logs" / f"{job}.research.txt").exists()); s.close()

    def _message(self, text, photo, with_assistant=True):
        import sqlite3 as _sq
        con = _sq.connect(self.tmp / "opencode.db"); con.execute("create table if not exists session_message (id text, session_id text, type text, seq int, time_created int, time_updated int, data text)")
        ctx = "<context>\nRight now it is Thursday. Tool hints.\n</context>\n\n"
        con.execute("insert into session_message (data) values (?)", (json.dumps({"time": {"created": 1}, "text": ctx + text + f"\n\n[Attached photo: {photo}]", "files": []}),))
        if with_assistant: con.execute("insert into session_message (data) values (?)", (json.dumps({"content": [{"toolInput": {"query": "REWRITE", "reference_photos": [str(photo)]}}]}),))
        con.commit(); con.close()

    def test_the_users_own_words_replace_the_chat_models_rewrite_when_photos_are_attached(self):
        inbox = self.tmp / "inbox"; inbox.mkdir(); a = inbox / "2026-11-20-aa.jpg"; a.write_bytes(b"x"); mine = "Make a 1 minute video, the red tights and boots stay consistent."
        self._message(mine, a); s = Server(self.tmp)
        parts, _ = s.call({"query": "REWRITE with black tights", "reference_photos": [str(a)]}, "generate_video"); job = parts[0]["async_job"]; s.done(job); args = self.agent_args(job)
        self.assertIn(mine, args); self.assertNotIn("REWRITE with black tights", args); self.assertNotIn("Attached photo", " ".join(args)); self.assertNotIn("<context>", " ".join(args))      # context block and photo lines are gone
        s.close()

    def test_without_the_message_or_a_photo_or_a_database_the_chat_models_query_is_used(self):
        inbox = self.tmp / "inbox"; inbox.mkdir(); a = inbox / "bb.jpg"; a.write_bytes(b"x"); s = Server(self.tmp)
        parts, _ = s.call({"query": "REWRITE", "reference_photos": [str(a)]}, "generate_video"); job = parts[0]["async_job"]; s.done(job); self.assertIn("REWRITE", self.agent_args(job))            # no database file at all
        self._message("another message", inbox / "other.jpg")
        parts, _ = s.call({"query": "REWRITE2", "reference_photos": [str(a)]}, "generate_video"); job = parts[0]["async_job"]; s.done(job); self.assertIn("REWRITE2", self.agent_args(job))         # no message with this photo
        c = inbox / "cc.jpg"; c.write_bytes(b"x"); self._message("my words", c)
        parts, _ = s.call({"query": "REWRITE3"}, "generate_video"); job = parts[0]["async_job"]; s.done(job); self.assertIn("REWRITE3", self.agent_args(job))                                   # no photo: nothing to look up
        (self.tmp / "opencode.db").write_bytes(b"not a database")
        parts, _ = s.call({"query": "REWRITE4", "reference_photos": [str(c)]}, "generate_video"); job = parts[0]["async_job"]; s.done(job); self.assertIn("REWRITE4", self.agent_args(job))         # a broken database is ignored
        s.close()

    def test_a_long_message_is_clipped_and_the_newest_message_with_the_photo_wins(self):
        inbox = self.tmp / "inbox"; inbox.mkdir(); a = inbox / "dd.jpg"; a.write_bytes(b"x"); self._message("old words", a, with_assistant=False); self._message("w" * 1500, a); s = Server(self.tmp)
        parts, _ = s.call({"query": "REWRITE", "reference_photos": [str(a)]}, "generate_video"); job = parts[0]["async_job"]; s.done(job); args = self.agent_args(job)
        self.assertIn("w" * 1000, args); self.assertNotIn("old words", args); self.assertNotIn("REWRITE", args); s.close()

    def test_the_stated_length_is_passed_to_the_agent_for_videos_only_and_checked(self):
        s = Server(self.tmp); tools = {t["name"]: t for t in s.rpc("tools/list")["result"]["tools"]}
        self.assertIn("seconds", tools["generate_video"]["inputSchema"]["properties"]); self.assertNotIn("seconds", tools["generate_image_set"]["inputSchema"]["properties"]); self.assertEqual(tools["generate_video"]["inputSchema"]["required"], ["query"])
        parts, _ = s.call({"query": "a couple in Paris", "seconds": 60}, "generate_video"); job = parts[0]["async_job"]; s.done(job); args = self.agent_args(job); self.assertEqual(args[args.index("--seconds") + 1], "60")
        parts, _ = s.call({"query": "no length"}, "generate_video"); job = parts[0]["async_job"]; s.done(job); self.assertNotIn("--seconds", self.agent_args(job))                 # nothing stated: nothing passed
        parts, _ = s.call({"query": "a set", "seconds": 60}, "generate_image_set"); job = parts[0]["async_job"]; s.done(job); self.assertNotIn("--seconds", self.agent_args(job))   # pictures ignore it
        for bad in (0, -5, 100000, "soon"): self.assertFalse(s.call({"query": "v", "seconds": bad}, "generate_video")[0][0]["ok"])
        s.close()

    def test_research_text_is_offered_on_the_video_tool_only(self):
        s = Server(self.tmp); tools = {t["name"]: t for t in s.rpc("tools/list")["result"]["tools"]}
        self.assertIn("research_text", tools["generate_video"]["inputSchema"]["properties"]); self.assertNotIn("research_text", tools["generate_image_set"]["inputSchema"]["properties"])
        self.assertEqual(tools["generate_video"]["inputSchema"]["required"], ["query"])
        parts, _ = s.call({"query": "a set", "research_text": "ignored"}, "generate_image_set"); job = parts[0]["async_job"]; s.done(job)
        self.assertFalse((self.tmp / "outbox" / "logs" / f"{job}.research.txt").exists()); s.close()

    def test_the_lock_is_held_while_the_job_runs_and_freed_after(self):
        s = Server(self.tmp, sleep="1.5"); first = s.call({"query": "pictures"})[0][0]; self.assertTrue(first["ok"])
        second = s.call({"query": "more pictures"})[0][0]; self.assertFalse(second["ok"]); self.assertIn("another picture set or video", second["error"])
        s.done(first["async_job"], timeout=20); time.sleep(0.3); self.assertTrue(s.call({"query": "again"})[0][0]["ok"]); s.close()

    def test_busy_lock_held_elsewhere(self):
        s = Server(self.tmp); held = open(self.tmp / "lock", "w"); fcntl.flock(held, fcntl.LOCK_EX)
        self.assertFalse(s.call({"query": "pictures"})[0][0]["ok"]); fcntl.flock(held, fcntl.LOCK_UN); self.assertTrue(s.call({"query": "pictures"})[0][0]["ok"]); s.close()

    def test_agent_failure_and_garbage_reach_the_outbox_as_clean_errors(self):
        s = Server(self.tmp, mode="fail"); job = s.call({"query": "x"})[0][0]["async_job"]; d = s.done(job); self.assertEqual((d["ok"], "ComfyUI" in d["error"]), (False, True)); s.close()
        t2 = Path(tempfile.mkdtemp()); s = Server(t2, mode="garbage"); job = s.call({"query": "x"})[0][0]["async_job"]; self.assertFalse(s.done(job)["ok"]); s.close()

    def test_a_single_picture_is_immediate_and_reports_shortening(self):
        s = Server(self.tmp); parts, err = s.call({"prompt": "a long description " * 60, "width": 1024, "height": 1024}, "generate_image"); r = parts[0]
        self.assertFalse(err); self.assertTrue(r["ok"] and r["backend"] == "comfyui" and r["seed"] == 7); f = Path(r["image_path"]); self.assertTrue(f.is_file()); self.assertEqual(f.parent, self.tmp / "images")
        self.assertTrue(f.name.startswith("img-")); self.assertIn("shortened", r["did"]); self.assertIn("on the GPU box", r["did"])
        parts, _ = s.call({"prompt": "a cat"}, "generate_image"); self.assertNotIn("shortened", parts[0]["did"]); s.close()
        s = Server(Path(tempfile.mkdtemp()), mode="fail"); parts, _ = s.call({"prompt": "a cat"}, "generate_image"); self.assertFalse(parts[0]["ok"]); self.assertIn("no GPU anywhere", parts[0]["error"]); s.close()

    def test_the_agent_is_given_a_progress_file_in_the_outbox(self):
        s = Server(self.tmp); job = s.call({"query": "pictures"})[0][0]["async_job"]; s.done(job)
        self.assertEqual((self.tmp / "progress_env.txt").read_text(), str(self.tmp / "outbox" / "progress" / f"{job}.json")); s.close()

    def test_a_cancel_marker_stops_the_agent_reports_it_and_frees_the_lock(self):
        s = Server(self.tmp, sleep="60"); job = s.call({"query": "pictures"})[0][0]["async_job"]; time.sleep(1.5)
        (self.tmp / "outbox" / "cancel").mkdir(parents=True, exist_ok=True); (self.tmp / "outbox" / "cancel" / job).write_text("1"); t0 = time.time()
        done = s.done(job, timeout=25); self.assertLess(time.time() - t0, 10)                                      # the 60 s stub was terminated, not waited for
        self.assertEqual((done["ok"], done.get("cancelled")), (False, True)); time.sleep(0.5)
        self.assertTrue(s.call({"query": "again"})[0][0]["ok"]); s.close()                                          # the lock was released with the runner

    # ---- synchronous mode (the default in production): the tool waits and returns what the bridge already understands
    def test_sync_set_returns_one_part_per_picture_with_captions_and_a_summary(self):
        s = Server(self.tmp, bg="sync"); parts, err = s.call({"query": "three pictures about rain", "count": 3}); self.assertFalse(err)
        imgs = [p for p in parts if "image_path" in p]; self.assertEqual([p["index"] for p in imgs], [1, 2, 3]); self.assertEqual(imgs[1]["caption"], "caption 2"); self.assertEqual(imgs[1]["topic"], "topic 2")
        for p in imgs: f = Path(p["image_path"]); self.assertTrue(f.is_file()); self.assertEqual(f.parent, self.tmp / "images"); self.assertTrue(f.name.startswith("imgset-20261116-test-"))
        self.assertTrue(parts[-1]["ok"] and "Made 3 pictures" in parts[-1]["did"] and "image_path" not in parts[-1] and "async_job" not in parts[-1])
        self.assertEqual(imgs[0]["secs"], 10.0); self.assertFalse((self.tmp / "outbox" / "done").exists()); s.close()                    # 30 s of picture time over 3 pictures; nothing is left in the outbox

    def test_sync_video_returns_a_video_path_the_bridge_can_send(self):
        s = Server(self.tmp, bg="sync"); parts, _ = s.call({"query": "how rainbows form"}, "generate_video"); r = parts[0]
        self.assertTrue(r["ok"] and "async_job" not in r); f = Path(r["video_path"]); self.assertTrue(f.is_file()); self.assertEqual(f.parent, self.tmp / "videos"); self.assertIn("Test video", r["did"]); s.close()

    def test_an_mcp_cancel_during_a_synchronous_call_stops_the_agent_frees_the_lock_and_sends_no_reply(self):
        """The Stop button: OpenCode aborts the call and sends notifications/cancelled. Before 2026-11-19 the server was blocked inside the tool and never read it, so the agent kept using the 3090."""
        s = Server(self.tmp, sleep="60", bg="sync"); stub = str(self.tmp / "stub.py")
        running = lambda: bool(subprocess.run(["pgrep", "-f", stub], capture_output=True, text=True).stdout.split())
        s.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "generate_image_set", "arguments": {"query": "pictures"}}}) + "\n"); s.p.stdin.flush()
        t0 = time.time()
        while not running() and time.time() - t0 < 10: time.sleep(0.1)
        self.assertTrue(running()); t0 = time.time()
        s.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 7, "reason": "stopped"}}) + "\n"); s.p.stdin.flush()
        while running() and time.time() - t0 < 30: time.sleep(0.2)
        self.assertFalse(running()); self.assertLess(time.time() - t0, 25)                                           # the 60 s stub was terminated, not waited for
        r = s.rpc("tools/list", ident=8); self.assertEqual(r["id"], 8)                                              # the first reply is the next request's: the cancelled call was not answered
        held = open(self.tmp / "lock", "w"); fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB); fcntl.flock(held, fcntl.LOCK_UN)   # the GPU lock was released
        s.close()

    def test_sync_failure_busy_and_the_lock_released_after(self):
        s = Server(self.tmp, mode="fail", bg="sync"); parts, _ = s.call({"query": "x"}); self.assertFalse(parts[0]["ok"]); self.assertIn("ComfyUI", parts[0]["error"]); s.close()
        t2 = Path(tempfile.mkdtemp()); s = Server(t2, bg="sync"); held = open(t2 / "lock", "w"); fcntl.flock(held, fcntl.LOCK_EX)
        self.assertIn("another picture set or video", s.call({"query": "x"})[0][0]["error"]); fcntl.flock(held, fcntl.LOCK_UN)
        self.assertTrue(s.call({"query": "x"})[0][0]["ok"]); self.assertTrue(s.call({"query": "y"})[0][0]["ok"]); s.close()                     # the lock is released after each synchronous job

    def test_the_flag_file_switches_the_mode_on_the_next_call_without_a_restart(self):
        s = Server(self.tmp, bg="flag"); sync_first = s.call({"query": "pictures", "count": 3})[0]; self.assertTrue(any("image_path" in p for p in sync_first))                # no flag: synchronous
        (self.tmp / "async_flag").write_text("1"); r = s.call({"query": "pictures"})[0][0]; self.assertTrue(r["ok"] and r["async_job"]); s.done(r["async_job"]); time.sleep(0.4)
        (self.tmp / "async_flag").unlink(); self.assertTrue(any("image_path" in p for p in s.call({"query": "pictures"})[0])); s.close()

    def test_tool_descriptions_match_the_mode(self):
        a = Server(self.tmp, bg="async"); b = Server(Path(tempfile.mkdtemp()), bg="sync")
        da = {t["name"]: t["description"] for t in a.rpc("tools/list")["result"]["tools"]}; db = {t["name"]: t["description"] for t in b.rpc("tools/list")["result"]["tools"]}
        for n in ("generate_image_set", "generate_video"): self.assertIn("RETURNS AT ONCE", da[n]); self.assertNotIn("RETURNS AT ONCE", db[n]); self.assertIn("when it returns", db[n])
        self.assertEqual(da["generate_image"], db["generate_image"]); a.close(); b.close()

    def test_unknown_method_and_notification(self):
        s = Server(self.tmp); self.assertEqual(s.rpc("nope")["error"]["code"], -32601)
        s.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"); s.p.stdin.flush()
        self.assertEqual(s.rpc("tools/list", ident=2)["id"], 2); s.close()


if __name__ == "__main__":
    unittest.main()
