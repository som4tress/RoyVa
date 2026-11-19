import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("prompt_length_guard", Path(__file__).resolve().parents[3] / "scripts" / "remote" / "comfy-prompt-guard" / "prompt_length_guard.py")
g = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(g)


class ServerGuardTests(unittest.TestCase):
    def graph(self): return {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "w " * 900, "clip": ["2", 0]}}, "2": {"class_type": "Anything", "inputs": {"value": "v " * 900, "seed": 3}}, "3": {"class_type": "KSampler", "inputs": {"steps": 20}}}

    def test_every_oversized_string_in_every_node_is_cut_and_short_values_are_left_alone(self):
        gr = self.graph(); rows = g.limit_graph(gr, 500)
        self.assertLessEqual(len(gr["1"]["inputs"]["text"]), 500); self.assertLessEqual(len(gr["2"]["inputs"]["value"]), 500)
        self.assertEqual((gr["1"]["inputs"]["clip"], gr["2"]["inputs"]["seed"], gr["3"]["inputs"]["steps"]), (["2", 0], 3, 20))
        self.assertEqual(sorted((r["was"], r["sent"] <= 500) for r in rows), [(1800, True), (1800, True)])

    def test_the_handler_modifies_the_graph_records_it_and_never_raises(self):
        with tempfile.TemporaryDirectory() as d:
            g.LOG = os.path.join(d, "prompt_guard.jsonl"); data = {"prompt": self.graph(), "client_id": "x"}
            out = g.on_prompt(data); self.assertIs(out, data); self.assertLessEqual(len(out["prompt"]["1"]["inputs"]["text"]), 500)
            self.assertEqual(len(open(g.LOG).read().splitlines()), 2)
            for weird in (None, {}, {"prompt": None}, {"prompt": {"1": "not a node", "2": {"inputs": None}}}):
                self.assertEqual(g.on_prompt(weird), weird)                       # a malformed submission is passed on untouched, never an exception
            g.LOG = "/nonexistent-dir/x.jsonl"; self.assertLessEqual(len(g.on_prompt({"prompt": self.graph()})["prompt"]["1"]["inputs"]["text"]), 500)       # a log failure does not stop the cut

    def test_the_default_ceiling_is_500(self): self.assertEqual(g.MAX_CHARS, 500)


if __name__ == "__main__":
    unittest.main()
