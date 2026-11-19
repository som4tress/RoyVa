import importlib.util
import logging
import os
import tempfile
import types
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("wan_timing_diag", Path(__file__).resolve().parents[3] / "scripts" / "remote" / "comfy-wan-diag" / "wan_timing_diag.py")
d = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(d)        # importing outside ComfyUI must not fail: every missing ComfyUI module is skipped


class Capture(logging.Handler):
    def __init__(self): super().__init__(); self.lines = []
    def emit(self, r): self.lines.append(r.getMessage())


class DiagNodeTests(unittest.TestCase):
    def setUp(self):
        self.cap = Capture(); logging.getLogger().addHandler(self.cap); self.old = logging.getLogger().level; logging.getLogger().setLevel(logging.INFO)
        self.tmp = tempfile.mkdtemp(); d.OFF_FILE = os.path.join(self.tmp, "off")

    def tearDown(self): logging.getLogger().removeHandler(self.cap); logging.getLogger().setLevel(self.old)

    def test_wrapper_is_behaviour_neutral_same_args_same_result_same_exception_and_logs_one_line(self):
        calls = []
        def fn(a, b=2, *rest, **kw): calls.append((a, b, rest, kw)); return a + b
        w = d.timed("thing", fn)
        self.assertEqual(w(1, 5, 7, k=3), 6); self.assertEqual(calls, [(1, 5, (7,), {"k": 3})])
        self.assertEqual(sum("[wan_timing_diag] thing" in x for x in self.cap.lines), 1)
        def boom(): raise ValueError("original")
        with self.assertRaises(ValueError) as c: d.timed("boom", boom)()
        self.assertEqual(str(c.exception), "original"); self.assertTrue(any("boom" in x for x in self.cap.lines))

    def test_off_file_switches_it_off_and_back_on_without_a_restart(self):
        w = d.timed("x", lambda: 1); self.cap.lines.clear()
        open(d.OFF_FILE, "w").close(); self.assertEqual(w(), 1); self.assertEqual(self.cap.lines, [])
        os.remove(d.OFF_FILE); self.assertEqual(w(), 1); self.assertEqual(len(self.cap.lines), 1)

    def test_install_wraps_class_methods_and_module_functions_once_and_skips_what_is_missing(self):
        class Patcher:
            def load(self, x): return x * 2
        mod = types.SimpleNamespace(Patcher=Patcher, sample=lambda: "s")
        mods = {"fake.mod": mod}
        def loader(p):
            if p not in mods: raise ImportError(p)
            return mods[p]
        targets = [("fake.mod", "Patcher", "load"), ("fake.mod", None, "sample"), ("fake.mod", "Patcher", "nope"), ("gone.mod", None, "x")]
        done, skipped = d.install(targets, loader); self.assertEqual(done, ["Patcher.load", "sample"]); self.assertEqual(len(skipped), 2)
        self.assertEqual(Patcher().load(4), 8); self.assertEqual(mod.sample(), "s")
        d.install(targets, loader); self.assertFalse(hasattr(Patcher.load.__wrapped__, "_wan_diag"))        # a second install does not stack wrappers
        self.cap.lines.clear(); Patcher().load(1); self.assertEqual(sum("Patcher.load" in x for x in self.cap.lines), 1)

    def test_nesting_is_shown_by_indentation(self):
        inner = d.timed("inner", lambda: 1); outer = d.timed("outer", lambda: inner()); self.cap.lines.clear(); outer()
        self.assertTrue(any("]   inner" in x for x in self.cap.lines)); self.assertTrue(any("] outer" in x for x in self.cap.lines))


if __name__ == "__main__":
    unittest.main()
