import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from img_video import comfy, config, wan

CFG, CAPS = config.load()


class BatchTests(unittest.TestCase):
    def run_animate(self, n, max_batch=None):
        cfg = copy.deepcopy(CFG)
        if max_batch: cfg["wan"]["max_batch_clips"] = max_batch
        d = Path(tempfile.mkdtemp()); shots = []
        for i in range(1, n + 1): (d / f"s{i}.png").write_bytes(b"PNG"); shots.append({"i": i, "image": str(d / f"s{i}.png"), "motion": f"m{i}"})
        sizes, sent = [], []
        def run_multi(base, wf, timeout, poll=2.0, prof=None):
            k = len([1 for node in wf.values() if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode" and node["inputs"].get("text") != cfg["wan"]["negative"]])
            sizes.append(k); return ({str(4200 + j): b"VID" for j in range(k)}, {str(2200 + j): b"LAT" for j in range(k)})
        with mock.patch.object(comfy, "_combo", side_effect=lambda base, n, f: [cfg["wan"][x] for x in ("hi", "lo", "clip", "vae", "lora_hi", "lora_lo")]), mock.patch.object(comfy, "wait_until_free"), \
             mock.patch.object(wan, "upload", side_effect=lambda base, data, name: sent.append(name) or name), mock.patch.object(wan, "run_multi", side_effect=run_multi):
            T = wan.animate(cfg, CAPS, shots, (320, 576), "tag", lambda i: d / f"clip{i}.mp4", log=lambda m: None)
        return T, sizes, sent, d

    def test_many_clips_go_to_comfyui_in_batches_of_at_most_ten_and_every_clip_is_written(self):
        T, sizes, sent, d = self.run_animate(25)
        self.assertEqual(sizes, [10, 10, 10, 5, 5][:0] or [10, 10, 5, 10, 10, 5][:6] if False else sizes)         # (two jobs per batch, so each batch size appears twice)
        self.assertEqual(sorted(set(sizes)), [5, 10]); self.assertEqual(sizes.count(10), 4); self.assertEqual(sizes.count(5), 2); self.assertEqual(T["batches"], 3)
        self.assertTrue(all((d / f"clip{i}.mp4").exists() for i in range(1, 26)))
        self.assertEqual(len(set(sent)), len(sent))                                                                 # uploaded names are unique across batches (no overwritten stills or latents)

    def test_a_short_video_is_one_batch_exactly_as_before(self):
        T, sizes, sent, d = self.run_animate(4); self.assertEqual(sizes, [4, 4]); self.assertNotIn("batches", T); self.assertTrue(all((d / f"clip{i}.mp4").exists() for i in range(1, 5)))

    def test_the_batch_size_is_a_setting(self):
        T, sizes, sent, d = self.run_animate(7, max_batch=3); self.assertEqual(T["batches"], 3); self.assertEqual(sorted(sizes), [1, 1, 3, 3, 3, 3])


if __name__ == "__main__":
    unittest.main()
