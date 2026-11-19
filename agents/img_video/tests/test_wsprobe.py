import unittest

from img_video import wsprobe

WF = {"1": {"class_type": "UNETLoader"}, "2": {"class_type": "CLIPTextEncode"}, "3": {"class_type": "KSamplerAdvanced"}, "4": {"class_type": "KSamplerAdvanced"}, "5": {"class_type": "SaveLatent"}}


def ev(t, ty, node=None, pid="p", v=None, mx=None): return (t, ty, pid, node, v, mx)


class SummarizeTests(unittest.TestCase):
    def test_node_seconds_and_sampler_steps(self):
        events = [ev(101, "execution_start", None), ev(102, "executing", "1"), ev(110, "executing", "2"), ev(112, "executing", "3"),
                  ev(150, "progress", "3", v=1, mx=1), ev(150.5, "executing", "4"), ev(158, "progress", "4", v=1, mx=2), ev(166, "progress", "4", v=2, mx=2), ev(166.2, "executing", "5"), ev(170, "executing", None)]
        r = wsprobe.summarize(WF, events, "p", 100.0, 171.0)
        self.assertEqual(r["total"], 71.0); self.assertEqual(r["queue_wait"], 2.0)
        self.assertEqual(r["by_class"]["UNETLoader"], 8.0); self.assertEqual(r["by_class"]["CLIPTextEncode"], 2.0)
        self.assertEqual(r["by_class"]["KSamplerAdvanced"], 38.5 + 15.7)
        s = r["samplers"]; self.assertEqual(s[0]["to_first_step"], 38.0); self.assertEqual(s[1]["to_first_step"], 7.5); self.assertEqual(s[1]["later_steps"], [8.0])
        line = wsprobe.describe("job B", r); self.assertIn("first sampler: 38.0s to its first step", line.replace("38s to", "38.0s to")); self.assertIn("job B", line)

    def test_other_jobs_events_and_empty_input_are_ignored(self):
        self.assertEqual(wsprobe.summarize(WF, [ev(1, "executing", "1", pid="other")], "p", 0.0, 2.0), {})
        self.assertIn("no per-node timing", wsprobe.describe("job A", {}))

    def test_a_dead_server_never_raises(self):
        p = wsprobe.Probe("http://127.0.0.1:9").start()
        self.assertFalse(p.ok); self.assertTrue(p.error); p.stop()


if __name__ == "__main__":
    unittest.main()
