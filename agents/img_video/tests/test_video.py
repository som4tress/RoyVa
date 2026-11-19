import unittest
from img_video import config, video, wan

CFG, CAPS = config.load()


class VideoTests(unittest.TestCase):
    def test_budget_follows_capabilities(self):
        v, p = CAPS["video"], CAPS["padding"]
        want = int(((v["frames"] / v["wan_fps"]) * v["max_slow"] - p["lead_seconds"] - p["tail_seconds"]) * config.cap(CAPS, "tts_chars_per_second"))
        self.assertEqual(video.narration_budget(CAPS), want)

    def test_xfade_chain(self):
        fg, vl, al = video.xfade_filter([5.0, 5.0, 5.0], 0.4)
        self.assertEqual((vl, al), ("v2", "a2"))
        self.assertIn("xfade=transition=fade:duration=0.4:offset=4.600", fg); self.assertIn("offset=9.200", fg)
        self.assertEqual(fg.count("acrossfade"), 2)

    def test_wan_workflows_use_configured_int8_names_and_one_expert_each(self):
        w = CFG["wan"]; shots = [{"prompt": "p", "image_name": "a.png", "seed": 1}, {"prompt": "q", "image_name": "b.png", "seed": 2}]
        hi = wan.hi_workflow(w, shots, 432, 432, 81); lo = wan.lo_workflow(w, shots, ["x.latent", "y.latent"], 432, 432, 81, 16)
        self.assertEqual(hi["1"]["inputs"]["unet_name"], w["hi"]); self.assertEqual(lo["1"]["inputs"]["unet_name"], w["lo"])
        self.assertIn("int8", w["hi"]); self.assertIn("int8", w["clip"])
        self.assertEqual([k for k in hi if k.startswith("220")], ["2200", "2201"]); self.assertEqual([k for k in lo if k.startswith("420")], ["4200", "4201"])
        self.assertFalse(any("/free" in str(v) for v in hi.values()))


if __name__ == "__main__":
    unittest.main()
