import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from img_video import comfy, config, guard, pipeline
from img_video.jobs import Job

CFG, CAPS = config.load()


class WarmTests(unittest.TestCase):
    def test_warm_runs_one_throwaway_1_step_picture_with_a_short_prompt_and_a_fresh_seed(self):
        graphs = []
        with mock.patch.object(comfy, "queue_state", return_value=(0, 0)), mock.patch.object(comfy, "run", side_effect=lambda b, wf, timeout=600, poll=1.0: graphs.append(wf) or b"png"):
            t = comfy.warm("http://box", CFG["comfy"]); comfy.warm("http://box", CFG["comfy"])
        self.assertIsNotNone(t); self.assertEqual(len(graphs), 2)
        g = graphs[0]
        self.assertEqual(g["6"]["inputs"]["steps"], 1); self.assertEqual((g["5"]["inputs"]["width"], g["5"]["inputs"]["height"]), (256, 256))
        self.assertLess(len(g["4"]["inputs"]["prompt"]), 500)
        self.assertNotEqual(graphs[0]["6"]["inputs"]["seed"], graphs[1]["6"]["inputs"]["seed"])          # same seed would be served from ComfyUI's cache without loading anything

    def test_warm_is_skipped_when_the_box_is_busy_or_the_backend_is_not_qwen(self):
        with mock.patch.object(comfy, "queue_state", return_value=(1, 0)), mock.patch.object(comfy, "run", side_effect=AssertionError("must not run")):
            self.assertIsNone(comfy.warm("http://box", CFG["comfy"]))
        with mock.patch.object(comfy, "queue_state", side_effect=AssertionError("must not look")):
            self.assertIsNone(comfy.warm("http://box", dict(CFG["comfy"], backend="z-image-turbo")))

    def test_should_warm_only_when_pictures_will_be_drawn_on_the_box(self):
        with tempfile.TemporaryDirectory() as d:
            job = Job.create(d, {"query": "q", "count": 3, "aspect": "1:1"}); on = {"pipeline": {"warm_pictures": True}, "image": {"backend": "comfy"}}
            self.assertTrue(pipeline.should_warm(on, job, None))
            self.assertFalse(pipeline.should_warm(on, job, "research")); self.assertFalse(pipeline.should_warm(on, job, "direct"))
            self.assertFalse(pipeline.should_warm(dict(on, image={"backend": "qwen-image-local"}), job, None))
            self.assertFalse(pipeline.should_warm({"pipeline": {"warm_pictures": False}, "image": {"backend": "comfy"}}, job, None))
            job.state["stages"]["images"] = {"status": "done"}; self.assertFalse(pipeline.should_warm(on, job, None))      # a resume with the pictures already drawn

    def test_background_warm_skips_quietly_when_the_gpu_lock_is_taken_and_holds_the_lock_while_it_runs(self):
        with tempfile.TemporaryDirectory() as d:
            job = Job.create(d, {"query": "q", "count": 3, "aspect": "1:1"}); lock = Path(d) / "gpu.lock"; seen = []
            with mock.patch.object(guard, "LOCK", lock):
                with guard.gpu_lock(wait_s=0), mock.patch.object(comfy, "warm", side_effect=AssertionError("must not run")):
                    pipeline._warm_pictures(job, CFG); [t.join(5) for t in threading.enumerate() if t.name == "warm-pictures"]
                def fake(base, c, log=None):
                    try:
                        with guard.gpu_lock(wait_s=0): seen.append("lock free")
                    except TimeoutError: seen.append("lock held")
                    return 1.0
                with mock.patch.object(comfy, "warm", fake):
                    pipeline._warm_pictures(job, CFG); [t.join(5) for t in threading.enumerate() if t.name == "warm-pictures"]
            log = (job.dir / "log.txt").read_text()
        self.assertIn("warm-up skipped", log); self.assertEqual(seen, ["lock held"]); self.assertIn("picture model loaded in 1s", log)


if __name__ == "__main__":
    unittest.main()
