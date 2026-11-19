import copy
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from img_video import comfy, config, director, guard, pipeline
from img_video.jobs import Job, fingerprint

CFG, CAPS = config.load()


def make_job(d, count=4):
    job = Job.create(d, {"query": "q", "count": count, "aspect": "1:1"}); job.write("plan.json", {"count": count, "needs_web": False, "research_questions": [], "tone": "x", "narrated": False}); job.write("research.json", [])
    return job


def fake_director(timeline, shots=4, pause=0.25, fail_after=None):
    def direct(job, cfg, caps, feed=None):
        try:
            feed(("style", "STYLE")); items = []
            for k in range(1, shots + 1):
                time.sleep(pause)
                if fail_after is not None and k > fail_after: raise RuntimeError("model could not produce a valid answer")
                it = {"topic": f"t{k}", "caption": f"c{k}", "image_prompt": f"p{k}"}; items.append(it); timeline.append(("shot", k, time.time())); feed(("shot", it))
            job.write("items.json", {"title": "T", "items": items}); job.write("direction.json", {"style_line": "STYLE"}); feed(("end",))
        except Exception as e:
            feed(("error", str(e))); raise
    return direct


def fake_render(timeline, secs=0.15):
    def gen(base, c, prompt, w, h, seed): time.sleep(secs); timeline.append(("img", prompt, time.time())); return b"PNG", secs
    return gen


class StreamingTests(unittest.TestCase):
    def run_stream(self, direct, **kw):
        timeline = []; d = tempfile.mkdtemp(); job = make_job(d); req = job.state["request"]; base = {"llm": "x"}
        with mock.patch.object(director, "direct", direct(timeline, **kw)), mock.patch.object(comfy, "preflight"), mock.patch.object(comfy, "wait_until_free"), \
             mock.patch.object(comfy, "generate_image", side_effect=fake_render(timeline)), mock.patch.object(guard, "LOCK", Path(d) / "gpu.lock"):
            t0 = time.time(); err = None
            try: pipeline._direct_and_images_streaming(job, CFG, CAPS, req, base, {"dir": "inputs"})
            except Exception as e: err = e
            return job, req, base, timeline, time.time() - t0, err

    def test_pictures_start_while_the_director_is_still_writing_and_the_whole_is_faster(self):
        job, req, base, tl, wall, err = self.run_stream(fake_director); self.assertIsNone(err)
        shots = [t for t in tl if t[0] == "shot"]; imgs = [t for t in tl if t[0] == "img"]
        self.assertEqual(len(imgs), 4); self.assertTrue(all((job.dir / "images" / f"{i:02d}.png").exists() for i in range(1, 5)))
        self.assertLess(imgs[0][2], shots[-1][2])                                  # the first picture was finished before the last shot was written
        self.assertLess(wall, 4 * 0.25 + 4 * 0.15 - 0.3)                           # one after the other would take 1.6 s
        st = job.state["stages"]; self.assertEqual((st["direct"]["status"], st["images"]["status"], st["images"]["streamed"]), ("done", "done", True))
        self.assertEqual(st["images"]["fp"], fingerprint(pipeline._images_inputs(base, CFG, req, job.read("items.json"), "STYLE")))     # same fingerprint as the sequential path: a resume reuses the pictures

    def test_the_prompts_and_seeds_are_the_same_as_in_the_sequential_path(self):
        job, req, base, tl, wall, err = self.run_stream(fake_director)
        prompts = [t[1] for t in tl if t[0] == "img"]; style_clause = f", STYLE, {CFG['policy']['image_text']}"
        self.assertEqual(prompts, [f"p{k}{style_clause}" for k in range(1, 5)])

    def test_a_director_failure_is_raised_as_the_directors_own_error_and_nothing_hangs(self):
        job, req, base, tl, wall, err = self.run_stream(fake_director, fail_after=2)
        self.assertIsInstance(err, RuntimeError); self.assertIn("valid answer", str(err)); self.assertLess(wall, 3)
        self.assertEqual(job.state["stages"]["direct"]["status"], "failed"); self.assertEqual(job.state["stages"]["images"]["status"], "failed")

    def test_feed_source_waits_for_the_first_shot_and_passes_errors_on(self):
        s = pipeline.FeedSource(); got = []
        t = threading.Thread(target=lambda: got.append(s.first())); t.start(); time.sleep(0.1); self.assertEqual(got, [])      # still waiting
        s.put(("style", "S")); time.sleep(0.05); self.assertEqual(got, []); s.put(("shot", {"topic": "a"})); t.join(1); self.assertEqual((got, s.style), ([True], "S"))
        s.put(("shot", {"topic": "b"})); s.put(("end",)); self.assertEqual([(k, x["topic"]) for k, x in s.items()], [(1, "a"), (2, "b")])
        e = pipeline.FeedSource(); e.put(("error", "boom")); self.assertRaises(RuntimeError, e.first)

    def test_streaming_is_only_used_for_the_3090_when_the_director_has_to_run_and_a_picture_stage_follows(self):
        with tempfile.TemporaryDirectory() as d:
            job = make_job(d); inp = {"x": 1}
            self.assertTrue(pipeline.should_stream(CFG, job, None, inp)); self.assertTrue(pipeline.should_stream(CFG, job, "images", inp))
            self.assertFalse(pipeline.should_stream(CFG, job, "direct", inp)); self.assertFalse(pipeline.should_stream(CFG, job, "research", inp))
            local = copy.deepcopy(CFG); local["image"]["backend"] = "qwen-image-local"; self.assertFalse(pipeline.should_stream(local, job, None, inp))      # this machine's GPU would compete with the writer
            off = copy.deepcopy(CFG); off["pipeline"] = {"stream_pictures": False}; self.assertFalse(pipeline.should_stream(off, job, None, inp))
            job.state["stages"]["direct"] = {"status": "done", "fp": fingerprint(inp)}; job.write("items.json", {}); job.write("direction.json", {})
            self.assertFalse(pipeline.should_stream(CFG, job, None, inp))                                                                          # a finished director is just read back


if __name__ == "__main__":
    unittest.main()
