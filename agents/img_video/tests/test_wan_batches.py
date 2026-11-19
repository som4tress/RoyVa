import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from img_video import comfy, config, wan

CFG, CAPS = config.load()


class BatchTests(unittest.TestCase):
    def run_animate(self, n, max_batch=None, two_pass=None):
        cfg = copy.deepcopy(CFG); self.order = []
        if two_pass is not None: cfg["wan"]["two_pass_batches"] = two_pass
        if max_batch: cfg["wan"]["max_batch_clips"] = max_batch
        d = Path(tempfile.mkdtemp()); shots = []
        for i in range(1, n + 1): (d / f"s{i}.png").write_bytes(b"PNG"); shots.append({"i": i, "image": str(d / f"s{i}.png"), "motion": f"m{i}"})
        sizes, sent = [], []
        def run_multi(base, wf, timeout, poll=2.0, prof=None):
            k = len([1 for node in wf.values() if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode" and node["inputs"].get("text") != cfg["wan"]["negative"]])
            sizes.append(k); self.order.append("hi" if any(isinstance(n, dict) and n.get("class_type") == "SaveLatent" for n in wf.values()) else "lo"); return ({str(4200 + j): b"VID" for j in range(k)}, {str(2200 + j): b"LAT" for j in range(k)})
        with mock.patch.object(comfy, "_combo", side_effect=lambda base, n, f: [cfg["wan"][x] for x in ("hi", "lo", "clip", "vae", "lora_hi", "lora_lo")]), mock.patch.object(comfy, "wait_until_free"), \
             mock.patch.object(wan, "upload", side_effect=lambda base, data, name: sent.append(name) or name), mock.patch.object(wan, "run_multi", side_effect=run_multi):
            T = wan.animate(cfg, CAPS, shots, (320, 576), "tag", lambda i: d / f"clip{i}.mp4", log=lambda m: None)
        return T, sizes, sent, d

    def test_many_clips_go_to_comfyui_in_batches_of_at_most_ten_and_every_clip_is_written(self):
        T, sizes, sent, d = self.run_animate(25)
        self.assertEqual(sorted(set(sizes)), [5, 10]); self.assertEqual(sizes.count(10), 4); self.assertEqual(sizes.count(5), 2); self.assertEqual(T["batches"], 3)
        self.assertTrue(all((d / f"clip{i}.mp4").exists() for i in range(1, 26)))
        self.assertEqual(len(set(sent)), len(sent))                                                                 # uploaded names are unique across batches (no overwritten stills or latents)

    def test_a_short_video_is_one_batch_exactly_as_before(self):
        T, sizes, sent, d = self.run_animate(4); self.assertEqual(sizes, [4, 4]); self.assertNotIn("batches", T); self.assertTrue(all((d / f"clip{i}.mp4").exists() for i in range(1, 5)))

    def test_the_batch_size_is_a_setting(self):
        T, sizes, sent, d = self.run_animate(7, max_batch=3); self.assertEqual(T["batches"], 3); self.assertEqual(sorted(sizes), [1, 1, 3, 3, 3, 3])

    def test_two_pass_runs_every_high_noise_job_before_any_low_noise_job_with_the_same_batches(self):
        T, sizes, sent, d = self.run_animate(25, two_pass=True)
        self.assertEqual(self.order, ["hi", "hi", "hi", "lo", "lo", "lo"]); self.assertEqual(sizes, [10, 10, 5, 10, 10, 5])      # same job sizes as before: only the order changes
        self.assertEqual(T["batches"], 3); self.assertTrue(all((d / f"clip{i}.mp4").exists() for i in range(1, 26)))
        self.assertEqual(len(set(sent)), len(sent)); self.assertTrue(all(k in T for k in ("job_a", "job_b", "upload_images", "upload_latents")))

    def test_the_old_order_is_still_available_and_a_short_video_never_changes(self):
        self.run_animate(25, two_pass=False); self.assertEqual(self.order, ["hi", "lo", "hi", "lo", "hi", "lo"])
        self.run_animate(4, two_pass=True); self.assertEqual(self.order, ["hi", "lo"])

    def test_each_low_noise_job_gets_the_latents_of_its_own_batch(self):
        cfg = copy.deepcopy(CFG); cfg["wan"]["two_pass_batches"] = True; cfg["wan"]["max_batch_clips"] = 2
        d = Path(tempfile.mkdtemp()); shots = []
        for i in range(1, 5): (d / f"s{i}.png").write_bytes(b"PNG"); shots.append({"i": i, "image": str(d / f"s{i}.png"), "motion": f"m{i}"})
        seen = []; n_hi = [0]
        def run_multi(base, wf, timeout, poll=2.0, prof=None):
            k = len([1 for node in wf.values() if isinstance(node, dict) and node.get("class_type") == "SaveLatent"])
            if k: n_hi[0] += 1; return ({}, {str(2200 + j): f"LAT{n_hi[0]}-{j}".encode() for j in range(k)})
            seen.append(sorted(n["inputs"]["latent"] for n in wf.values() if isinstance(n, dict) and n.get("class_type") == "LoadLatent")); return ({str(4200 + j): b"VID" for j in range(2)}, {})
        uploaded = {}
        with mock.patch.object(comfy, "_combo", side_effect=lambda base, n, f: [cfg["wan"][x] for x in ("hi", "lo", "clip", "vae", "lora_hi", "lora_lo")]), mock.patch.object(comfy, "wait_until_free"), \
             mock.patch.object(wan, "upload", side_effect=lambda base, data, name: uploaded.__setitem__(name, data) or name), mock.patch.object(wan, "run_multi", side_effect=run_multi):
            wan.animate(cfg, CAPS, shots, (320, 576), "tag", lambda i: d / f"clip{i}.mp4", log=lambda m: None)
        self.assertEqual([[uploaded[n] for n in names] for names in seen], [[b"LAT1-0", b"LAT1-1"], [b"LAT2-0", b"LAT2-1"]])


if __name__ == "__main__":
    unittest.main()


class RetryTests(unittest.TestCase):
    def test_a_name_lookup_glitch_is_retried_but_other_errors_are_not(self):
        import socket, urllib.error
        calls = []
        def flaky():
            calls.append(1)
            if len(calls) < 3: raise urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
            return "ok"
        self.assertEqual(comfy.retrying(flaky, waits=(0, 0, 0)), "ok"); self.assertEqual(len(calls), 3)
        def always(): raise urllib.error.URLError(socket.gaierror(-2, "x"))
        with self.assertRaises(urllib.error.URLError): comfy.retrying(always, waits=(0, 0))             # gives up after the waits
        n = []
        def timeout():
            n.append(1); raise urllib.error.URLError(TimeoutError("timed out"))
        with self.assertRaises(urllib.error.URLError): comfy.retrying(timeout, waits=(0, 0, 0))
        self.assertEqual(len(n), 1)                                                                     # a request that may have been sent is never repeated
        h = []
        def http():
            h.append(1); raise urllib.error.HTTPError("u", 400, "bad", {}, None)
        with self.assertRaises(urllib.error.HTTPError): comfy.retrying(http, waits=(0, 0))
        self.assertEqual(len(h), 1)
