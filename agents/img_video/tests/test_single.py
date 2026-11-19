import tempfile
import unittest
from pathlib import Path
from unittest import mock

from img_video import comfy, config, guard, llm, local_sd, single

CFG, CAPS = config.load()


class SingleTests(unittest.TestCase):
    def run_it(self, prompt, **kw):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(config, "jobs_dir", return_value=Path(d)), mock.patch.object(guard, "LOCK", Path(d) / "gpu.lock"):
            r = single.make_image(CFG, CAPS, prompt, **kw)
            if r["ok"]: r["bytes"] = Path(r["image_path"]).read_bytes()
            return r

    def test_short_prompt_goes_to_the_3090_as_written(self):
        seen = []
        with mock.patch.object(comfy, "preflight"), mock.patch.object(comfy, "generate_image", side_effect=lambda b, c, p, w, h, s: seen.append((p, w, h)) or (b"PNG", 3.0)):
            r = self.run_it("a red fox in the snow", aspect="1:1")
        self.assertTrue(r["ok"] and r["backend"] == "3090" and r["method"] == "none" and r["bytes"] == b"PNG"); self.assertEqual(seen[0][0], "a red fox in the snow")

    def test_a_big_prompt_is_shortened_before_the_3090_sees_it(self):
        seen = []
        with mock.patch.object(comfy, "preflight"), mock.patch.object(comfy, "generate_image", side_effect=lambda b, c, p, w, h, s: seen.append(p) or (b"PNG", 3.0)), \
             mock.patch.object(llm, "ask_json", return_value={"prompt": "a short version"}):
            r = self.run_it("very long " * 300)
        self.assertEqual((r["method"], seen), ("rewrite", ["a short version"])); self.assertGreater(r["original_chars"], 2000)

    def test_an_unreachable_3090_falls_back_to_this_machines_gpu(self):
        with mock.patch.object(comfy, "preflight", side_effect=comfy.ComfyError("down")), mock.patch.object(local_sd, "preflight"), \
             mock.patch.object(local_sd, "generate_image", return_value=(b"LOCAL", 80.0)):
            r = self.run_it("a sloth")
        self.assertTrue(r["ok"] and r["backend"] == "local" and r["bytes"] == b"LOCAL" and "3090 was not used" in r["note"])

    def test_a_busy_3090_falls_back_instead_of_queueing_a_second_job(self):
        with tempfile.TemporaryDirectory() as d:
            lock = Path(d) / "gpu.lock"
            with mock.patch.object(guard, "LOCK", lock), guard.gpu_lock(wait_s=0):
                real = guard.gpu_lock
                with mock.patch.object(comfy, "preflight"), mock.patch.object(comfy, "generate_image", side_effect=AssertionError("3090 must not be used")), \
                     mock.patch.object(guard, "gpu_lock", lambda wait_s=15, log=None: real(wait_s=0.1, log=log)), mock.patch.object(local_sd, "preflight"), \
                     mock.patch.object(local_sd, "generate_image", return_value=(b"LOCAL", 80.0)), mock.patch.object(config, "jobs_dir", return_value=Path(d)):
                    r = single.make_image(CFG, CAPS, "a sloth")
        self.assertTrue(r["ok"] and r["backend"] == "local")

    def test_a_failure_everywhere_is_a_clean_error_not_a_crash(self):
        with mock.patch.object(comfy, "preflight", side_effect=comfy.ComfyError("down")), mock.patch.object(local_sd, "preflight", side_effect=RuntimeError("no model")):
            r = self.run_it("a sloth")
        self.assertFalse(r["ok"]); self.assertIn("no model", r["error"])


if __name__ == "__main__":
    unittest.main()
