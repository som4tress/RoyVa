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


class FitSizeTests(unittest.TestCase):
    def test_a_video_over_the_upload_limit_is_re_encoded_to_fit_and_a_small_one_is_untouched(self):
        import pathlib, subprocess, tempfile
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "v.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=6", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-c:v", "libx264", "-crf", "5", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(f)], check=True)
            big = f.stat().st_size; limit = big // 2
            self.assertFalse(video.fit_size(f, big + 1))                     # already small enough: not touched
            self.assertEqual(f.stat().st_size, big)
            self.assertTrue(video.fit_size(f, limit))
            self.assertLessEqual(f.stat().st_size, limit)
            self.assertAlmostEqual(video._dur(f), 6.0, delta=0.3)           # same length, sound kept
            self.assertIn("aac", subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(f)]).decode())


class RateCapTests(unittest.TestCase):
    def test_the_cap_follows_length_and_leaves_room_for_audio(self):
        a = video.rate_cap_args([5.0] * 25, 0.4, 48 * 1024 * 1024, True)
        secs = 25 * 5.0 - 24 * 0.4
        v = int(a[1]); self.assertLess((v + 160_000) * secs / 8, 48 * 1024 * 1024)            # video + audio fit the limit
        self.assertEqual(a[0], "-maxrate"); self.assertEqual(int(a[3]), 2 * v)
        short = video.rate_cap_args([5.0] * 4, 0.4, 48 * 1024 * 1024, True)
        self.assertGreater(int(short[1]), 5 * v)                                              # a short video is effectively uncapped (crf 18 decides)
        self.assertGreater(int(video.rate_cap_args([5.0] * 25, 0.4, 48 * 1024 * 1024, False)[1]), v)   # no audio track: more room
