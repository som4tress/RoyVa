import json
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from img_video import config, director, llm, pipeline, video
from img_video.jobs import Job

CFG, CAPS = config.load()


def plan_reply(narrated=None):
    o = {"count": 2, "needs_web": False, "research_questions": [], "tone": "calm", "visual_style": "flat"}
    if narrated is not None: o["narrated"] = narrated
    return o


class ModeTests(unittest.TestCase):
    def _plan(self, req, narrated):
        with tempfile.TemporaryDirectory() as d:
            job = Job.create(d, req)
            with mock.patch.object(llm, "ask_json", return_value=plan_reply(narrated)) as m:
                pipeline.plan(job, CFG, CAPS)
            return job.read("plan.json")["narrated"], m.call_args[0][2]

    def test_only_a_video_can_be_narrated_and_the_planner_decides(self):
        self.assertEqual(self._plan({"query": "q", "aspect": "1:1", "video": True}, True)[0], True)
        self.assertEqual(self._plan({"query": "q", "aspect": "1:1", "video": True}, False)[0], False)
        self.assertEqual(self._plan({"query": "q", "aspect": "1:1", "video": True}, None)[0], False)      # no answer means silent
        n, prompt = self._plan({"query": "q", "aspect": "1:1"}, True)                                        # a set of pictures is never narrated, and the planner is not even asked
        self.assertFalse(n); self.assertNotIn("narrated", prompt)
        self.assertIn("narrated", self._plan({"query": "q", "aspect": "1:1", "video": True}, True)[1])

    def test_a_video_is_cut_to_the_length_limit_and_a_set_is_not(self):
        import copy
        c30 = copy.deepcopy(CFG); c30["limits"]["max_video_seconds"] = 30
        self.assertEqual((video.max_shots(c30, CAPS, False), video.max_shots(c30, CAPS, True)), (6, 4))              # 30 s: 6 silent or 4 narrated shots
        self.assertEqual((video.max_shots(CFG, CAPS, False), video.max_shots(CFG, CAPS, True)), (25, 20)); self.assertEqual(CFG["limits"]["max_video_seconds"], 120)      # the configured cap: 2 minutes
        self.assertGreaterEqual(CFG["limits"]["max_images"], video.max_shots(CFG, CAPS, False))                       # the plan's own count limit must allow a full-length video
        for narrated, most in ((False, 6), (True, 4)):
            with tempfile.TemporaryDirectory() as d:
                job = Job.create(d, {"query": "q", "aspect": "1:1", "video": True, "count": 10})
                with mock.patch.object(llm, "ask_json", return_value={**plan_reply(narrated), "count": 10}): pipeline.plan(job, c30, CAPS)
                self.assertEqual(job.read("plan.json")["count"], most)
        with tempfile.TemporaryDirectory() as d:
            job = Job.create(d, {"query": "q", "aspect": "1:1", "count": 10})                                          # a picture set keeps its 10
            with mock.patch.object(llm, "ask_json", return_value={**plan_reply(None), "count": 10}): pipeline.plan(job, CFG, CAPS)
            self.assertEqual(job.read("plan.json")["count"], 10)

    def test_shot_format_asks_only_for_what_the_output_needs(self):
        both, motion_only, neither = director.shot_format(True, True), director.shot_format(True, False), director.shot_format(False, False)
        self.assertIn('"motion"', both); self.assertIn('"narration"', both)
        self.assertIn('"motion"', motion_only); self.assertNotIn('"narration"', motion_only)
        self.assertNotIn('"motion"', neither); self.assertNotIn('"narration"', neither); self.assertTrue(neither.endswith('no hashtags).'))
        chk = director._shot_check(50, None, False, False); ok = {"scene": {"subject": "s", "setting": "t", "colors": "c"}, "caption": "c"}
        self.assertIsNone(chk(ok)); self.assertIn("motion needed", director._shot_check(50, None, True, False)(ok))

    def test_silent_assemble_has_no_audio_track(self):
        if not shutil.which("ffmpeg"): self.skipTest("ffmpeg missing")
        with tempfile.TemporaryDirectory() as d:
            job = Job.create(d, {"query": "q", "aspect": "1:1", "video": True}); vd = video.vdir(job)
            for i in (1, 2):
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=16:duration=2", "-pix_fmt", "yuv420p", str(vd / f"clip{i}.mp4")], check=True)
            job.write("video/storyboard.json", {"title": "t", "narrated": False, "out": [64, 64], "wan": [64, 64], "shots": [{"i": 1}, {"i": 2}]})
            video.assemble(job, CFG, CAPS)
            out = vd / "video.mp4"; self.assertTrue(out.exists() and out.stat().st_size > 0)
            streams = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)]).decode().split()
            self.assertEqual(streams, ["video"]); self.assertEqual(job.read("video.json")["cut_lines"], [])


if __name__ == "__main__":
    unittest.main()
