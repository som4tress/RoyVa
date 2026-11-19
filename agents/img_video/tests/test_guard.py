import tempfile
import unittest
from pathlib import Path
from unittest import mock

from img_video import config, guard, llm

CFG, CAPS = config.load()


class GuardTests(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(); p = mock.patch.object(guard, "AUDIT", Path(self._d.name) / "prompts_sent.jsonl"); p.start(); self.addCleanup(p.stop); self.addCleanup(self._d.cleanup)

    def test_cut_is_at_a_word_boundary(self):
        self.assertEqual(guard.cut("alpha beta gamma delta", 12), "alpha beta"); self.assertEqual(guard.cut("short", 50), "short"); self.assertEqual(guard.cut("x" * 40, 10), "x" * 10)

    def test_fit_prompt_leaves_a_short_prompt_alone_and_never_calls_the_writer(self):
        with mock.patch.object(llm, "ask_json", side_effect=AssertionError("no writer call for a short prompt")):
            r = guard.fit_prompt(CFG, "a red fox in the snow", cap=500)
        self.assertEqual((r["method"], r["prompt"]), ("none", "a red fox in the snow"))

    def test_fit_prompt_rewrites_a_big_prompt_through_the_writer(self):
        big = "a very detailed scene " * 120
        with mock.patch.object(llm, "ask_json", return_value={"prompt": "a detailed scene"}):
            r = guard.fit_prompt(CFG, big, cap=200)
        self.assertEqual((r["method"], r["prompt"], r["original_chars"]), ("rewrite", "a detailed scene", len(big.strip())))

    def test_fit_prompt_falls_back_to_a_cut_when_the_writer_is_down_or_ignores_the_cap(self):
        big = "word " * 400; logs = []
        for patch in (mock.patch.object(llm, "ask_json", side_effect=llm.LLMError("down")), mock.patch.object(llm, "ask_json", return_value={"prompt": big})):
            with patch:
                r = guard.fit_prompt(CFG, big, cap=200, log=logs.append)
            self.assertEqual(r["method"], "trim"); self.assertLessEqual(len(r["prompt"]), 200); self.assertFalse(r["prompt"].endswith("wor"))
        self.assertTrue(any("trimmed at a word boundary" in x for x in logs))

    def test_trim_workflow_cuts_a_long_string_in_any_node_not_only_in_text_encoders(self):
        wf = {"1": {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "w " * 900}}, "2": {"class_type": "SomeFutureEncoder", "inputs": {"text": "t " * 900, "seed": 5}}}
        self.assertEqual(guard.trim_workflow(wf, 500), 2); self.assertLessEqual(len(wf["1"]["inputs"]["value"]), 500); self.assertLessEqual(len(wf["2"]["inputs"]["text"]), 500); self.assertEqual(wf["2"]["inputs"]["seed"], 5)

    def test_trim_workflow_cuts_every_oversized_string_and_leaves_short_ones(self):
        wf = {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "w " * 900}}, "2": {"class_type": "TextEncodeQwenImage21", "inputs": {"prompt": "p " * 900}},
              "3": {"class_type": "SaveImage", "inputs": {"filename_prefix": "f" * 900}}, "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "short"}}}
        self.assertEqual(guard.trim_workflow(wf, 800), 3)                                     # any string over the ceiling, whatever the node
        self.assertLessEqual(len(wf["1"]["inputs"]["text"]), 800); self.assertLessEqual(len(wf["2"]["inputs"]["prompt"]), 800)
        self.assertLessEqual(len(wf["3"]["inputs"]["filename_prefix"]), 800); self.assertEqual(wf["4"]["inputs"]["text"], "short")

    def test_gpu_lock_is_exclusive_and_released(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(guard, "LOCK", Path(d) / "gpu.lock"):
            with guard.gpu_lock(wait_s=0):
                with self.assertRaises(TimeoutError):
                    with guard.gpu_lock(wait_s=0.1): pass
            with guard.gpu_lock(wait_s=0): pass                  # free again after the first holder left

    def test_nothing_over_the_cap_is_ever_posted_to_the_3090_by_either_client_and_every_prompt_is_recorded(self):
        from img_video import comfy, wan
        import json, urllib.error
        cap = CFG["limits"]["image_prompt_chars"]; posted = []
        wf = lambda: {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "w " * 900}}, "2": {"class_type": "TextEncodeQwenImage21", "inputs": {"prompt": "p " * 900}}, "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "short"}}}
        class R:
            def __init__(self, d=b'{"prompt_id": "x"}'): self.d = d
            def read(self, n=None): return self.d
            def __enter__(self): return self
            def __exit__(self, *a): return False
        def fake(req, timeout=0): posted.append(json.loads(req.data)); return R()
        comfy._HARD.clear()
        with mock.patch.object(comfy.urllib.request, "urlopen", fake): comfy._call("http://box:8188", "/prompt", {"prompt": wf()})
        with mock.patch.object(wan.urllib.request, "urlopen", fake), mock.patch.object(wan.time, "sleep", side_effect=RuntimeError("stop after posting")):
            try: wan.run_multi("http://box:8188", wf(), 5)
            except RuntimeError: pass
        self.assertEqual(len(posted), 2)
        for body in posted:
            for node in body["prompt"].values(): self.assertLessEqual(len(next(iter(node["inputs"].values()))), cap)
        rows = [json.loads(l) for l in guard.AUDIT.read_text().splitlines()]
        self.assertEqual(len(rows), 6); self.assertTrue(all(r["sent"] <= cap for r in rows)); self.assertEqual(sorted({r["was"] for r in rows}), [5, 1800])

    def test_the_ceiling_can_never_be_above_the_cap_even_if_the_config_says_so(self):
        from img_video import comfy
        comfy._HARD.clear(); bad = {"limits": {"hard_prompt_chars": 800, "image_prompt_chars": 500}}
        with mock.patch.object(comfy.config, "load", return_value=(bad, CAPS)): self.assertEqual(comfy._hard(), 500)
        comfy._HARD.clear()
        self.assertLessEqual(comfy._hard(), CFG["limits"]["image_prompt_chars"]); comfy._HARD.clear()


if __name__ == "__main__":
    unittest.main()
