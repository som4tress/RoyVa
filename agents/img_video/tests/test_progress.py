import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from img_video import comfy, config, progress
from img_video.jobs import Job

CFG, CAPS = config.load()


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.f = Path(self.d.name) / "p.json"; progress.reset()
        p = mock.patch.dict(os.environ, {"IMG_VIDEO_PROGRESS_FILE": str(self.f)}); p.start(); self.addCleanup(p.stop); self.addCleanup(self.d.cleanup); self.addCleanup(progress.reset)

    def read(self): return json.loads(self.f.read_text())

    def test_stages_and_counters_are_written_atomically_and_accumulate(self):
        progress.stage("plan", "running"); progress.stage("plan", "done"); progress.stage("direct", "running"); progress.update(shots_done=2, shots_total=5, pictures_done=1, pictures_total=5)
        p = self.read(); self.assertEqual(p["stages"], {"plan": "done", "direct": "running"}); self.assertEqual((p["shots_done"], p["pictures_done"], p["pictures_total"]), (2, 1, 5)); self.assertIn("ts", p)
        self.assertFalse(Path(str(self.f) + ".tmp").exists())

    def test_nothing_is_written_without_the_variable_and_a_bad_path_never_breaks_a_render(self):
        with mock.patch.dict(os.environ, {}, clear=False): os.environ.pop("IMG_VIDEO_PROGRESS_FILE"); progress.update(x=1); self.assertFalse(self.f.exists())
        with mock.patch.dict(os.environ, {"IMG_VIDEO_PROGRESS_FILE": "/nonexistent-dir/p.json"}): progress.update(x=1)

    def test_every_stage_of_a_job_is_reported_including_reused_ones(self):
        job = Job.create(self.d.name, {"query": "q", "aspect": "1:1"})
        job.run_stage("plan", {"a": 1}, lambda: job.write("plan.json", {}), ["plan.json"]); job.run_stage("plan", {"a": 1}, lambda: None, ["plan.json"])
        self.assertEqual(self.read()["stages"], {"plan": "done"})

    def test_interrupt_asks_comfyui_to_stop_and_never_raises(self):
        with mock.patch.object(comfy, "_call") as c: self.assertTrue(comfy.interrupt("http://box:8188")); self.assertEqual(c.call_args[0][:2], ("http://box:8188", "/interrupt"))
        with mock.patch.object(comfy, "_call", side_effect=OSError("down")): self.assertFalse(comfy.interrupt("http://box:8188"))


if __name__ == "__main__":
    unittest.main()
