import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from img_video import config, director, llm
from img_video.jobs import Job

CFG, CAPS = config.load()
SCENE = {"subject": "A person stands with their back to the sun, facing the rain", "setting": "a wet field, wide shot from behind", "colors": "yellow sun, grey rain, low light"}


def fake(c, system, user, temperature=0.6, max_tokens=4000, check=None):
    if "plans a set" in system or "before anything is drawn. First" in system:
        o = {"intent": "i", "audience": "a", "rules": ["sun behind observer"], "open_details": ["sun color"], "title": "T", "shot_list": [{"topic": f"t{i}", "purpose": "p"} for i in range(1, 4)]}
    elif "fixing every open detail" in system:
        o = {"decisions": [{"detail": "sun color", "value": "yellow"}], "style": {"look": "photo", "palette": "warm", "lighting": "low sun", "camera": "wide"}, "recurring": []}
    elif "shorten text" in system:
        o = {k: "short phrase" for k in director.SCENE}
    else:
        o = {"rules_applied": "r", "scene": dict(SCENE), "caption": "cap", "motion": "slow pan", "narration": "short line"}
    if check:
        assert check(o) is None, check(o)
    return o


class DirectorTests(unittest.TestCase):
    def test_full_plan_with_fake_model(self):
        with tempfile.TemporaryDirectory() as d:
            job = Job.create(d, {"query": "q", "count": 3, "aspect": "1:1"})
            job.write("plan.json", {"count": 3, "needs_web": False, "research_questions": [], "tone": "calm"}); job.write("research.json", [])
            with mock.patch.object(llm, "ask_json", fake):
                director.direct(job, CFG, CAPS)
            dr, it = job.read("direction.json"), job.read("items.json")
            self.assertEqual(len(dr["shots"]), 3); self.assertEqual(len(it["items"]), 3)
            self.assertNotIn("revised", dr["shots"][1])
            self.assertIn("Colors: yellow sun, grey rain, low light.", it["items"][0]["image_prompt"]); self.assertEqual(dr["style_line"], "photo, warm, low sun, wide")

    def test_analyze_accepts_object_for_list_fields_without_a_retry(self):
        calls = []
        def one_shot(c, system, user, temperature=0.6, max_tokens=4000, check=None):
            calls.append(1)
            o = {"intent": "i", "audience": "a", "rules": {"light": "from the left"}, "open_details": {"lighting": "varies", "pose": "facing left"}, "title": "T", "shot_list": [{"topic": f"t{i}", "purpose": "p"} for i in range(1, 4)]}
            assert check(o) is None, check(o)
            return o
        with mock.patch.object(llm, "ask_json", one_shot), tempfile.TemporaryDirectory() as d:
            job = Job.create(d, {"query": "q", "count": 3, "aspect": "1:1"})
            an = director.analyze(job, CFG, CAPS, {"count": 3, "needs_web": False, "research_questions": [], "tone": "calm"}, {"query": "q"}, [], 3, "")
        self.assertEqual(an["open_details"], ["lighting: varies", "pose: facing left"]); self.assertEqual(an["rules"], ["light: from the left"]); self.assertEqual(len(calls), 1)

    def test_shot_check_enforces_narration_budget(self):
        chk = director._shot_check(50); ok = {"scene": dict(SCENE), "caption": "c", "motion": "m", "narration": "x" * 50}
        self.assertIsNone(chk(ok)); self.assertIsNone(chk({**ok, "narration": "x" * 55})); self.assertIn("at most 50", chk({**ok, "narration": "x" * 56}))
        self.assertIn("scene needs", chk({**ok, "scene": {**SCENE, "colors": ""}}))

    def test_scene_and_style_length_caps(self):
        long_scene = {**SCENE, "subject": "x" * 900}
        chk = director._shot_check(50, 400); ok = {"scene": dict(SCENE), "caption": "c", "motion": "m", "narration": "short"}
        self.assertIsNone(chk(ok)); self.assertIn("scene is too long", chk({**ok, "scene": long_scene})); self.assertIsNone(director._shot_check(50)({**ok, "scene": long_scene}))
        self.assertNotIn("#", director.style_line({"look": "flat (#112233)", "palette": "blue #AABBCC", "lighting": "soft", "camera": "iso"}))

    def test_fit_scene_rewrites_then_trims_at_word_boundary_never_fails(self):
        lim = director.field_limits(300); big = {k: "word " * 60 for k in director.SCENE}; logs = []
        with mock.patch.object(llm, "ask_json", fake):                                # the model shortens every field
            ok = director.fit_scene(CFG, big, lim, 300, logs.append)
        self.assertEqual(ok["subject"], "short phrase"); self.assertTrue(any("scene rewrite 1" in x for x in logs))
        fits = dict(SCENE); self.assertEqual(director.fit_scene(CFG, fits, lim, 600), fits)       # already fits: untouched, no model call
        logs = []
        with mock.patch.object(llm, "ask_json", return_value=big):                    # the model never gets it short enough: trim, do not fail
            cut = director.fit_scene(CFG, big, lim, 300, logs.append)
        self.assertLessEqual(len(director.image_prompt(cut).rstrip(". ")), 300); self.assertTrue(any("trimmed at a word boundary" in x for x in logs))
        for k in director.SCENE: self.assertTrue(big[k].startswith(cut[k]) and (len(cut[k]) == len(big[k]) or big[k][len(cut[k])] == " "))     # cut only at a word end
        with mock.patch.object(llm, "ask_json", side_effect=llm.LLMError("down")):    # model unavailable: still trimmed, still no failure
            self.assertLessEqual(len(director.image_prompt(director.fit_scene(CFG, big, lim, 300)).rstrip(". ")), 300)

    def test_fit_style_trims_instead_of_failing(self):
        st = {"look": "a " * 80, "palette": "b " * 60, "lighting": "c " * 40, "camera": "d " * 20}
        with mock.patch.object(llm, "ask_json", side_effect=llm.LLMError("down")):
            out = director.fit_style(CFG, st, 100)
        self.assertLessEqual(len(director.style_line(out)), 115)

    def test_director_saves_each_step_and_records_how_each_scene_was_fitted(self):
        calls = {"n": 0}
        def fake2(c, system, user, temperature=0.6, max_tokens=4000, check=None):
            o = fake(c, system, user, temperature, max_tokens, None)
            if "ONE shot" in system:
                calls["n"] += 1
                if calls["n"] == 1: o = {**o, "scene": {**o["scene"], "subject": "x " * 400}}              # the writer overshoots on the first shot only
            if check: assert check(o) is None, check(o)
            return o
        with tempfile.TemporaryDirectory() as d:
            job = Job.create(d, {"query": "q", "count": 3, "aspect": "1:1"})
            job.write("plan.json", {"count": 3, "needs_web": False, "research_questions": [], "tone": "calm"}); job.write("research.json", [])
            logs = []; job.log = logs.append
            with mock.patch.object(llm, "ask_json", fake2):
                director.direct(job, CFG, CAPS)
            for f in ("01_analyze", "02_decide", "03_budget", "04_shots"): self.assertTrue((job.dir / "director" / f"{f}.json").exists(), f)
            sh = job.read("direction.json")["shots"]
            self.assertEqual([x["fit"] for x in sh], ["rewrite", "none", "none"]); self.assertIn("scene_raw", sh[0]); self.assertNotIn("scene_raw", sh[1])
            self.assertEqual(len(sh[0]["scene_raw"]["subject"]), 800); self.assertTrue(any(x.startswith("  shot 1: scene rewrite 1") for x in logs))      # the log names the shot
            bud = job.read("director/03_budget.json"); self.assertEqual(bud["cap"], CFG["limits"]["image_prompt_chars"]); self.assertEqual(set(bud["limits"]), set(director.SCENE))

    def test_scene_weights_come_from_config_and_fall_back_when_they_do_not_name_the_fields(self):
        cfg = {"director": {"scene_weights": {"subject": 0.8, "setting": 0.1, "colors": 0.1}}}
        self.assertEqual(director._weights(cfg)["subject"], 0.8); self.assertEqual(director._weights({"director": {"scene_weights": {"subject": 1.0}}}), director.WEIGHT); self.assertEqual(director._weights({}), director.WEIGHT)
        self.assertGreater(director.field_limits(300, director._weights(cfg))["subject"], director.field_limits(300)["subject"])

    def test_final_prompt_fits_cap(self):
        with tempfile.TemporaryDirectory() as d:
            job = Job.create(d, {"query": "q", "count": 3, "aspect": "1:1"})
            job.write("plan.json", {"count": 3, "needs_web": False, "research_questions": [], "tone": "calm"}); job.write("research.json", [])
            with mock.patch.object(llm, "ask_json", fake):
                director.direct(job, CFG, CAPS)
            dr, it = job.read("direction.json"), job.read("items.json")
            cap = CFG["limits"]["image_prompt_chars"]
            for x in it["items"]: self.assertLessEqual(len(f"{x['image_prompt'].rstrip('. ')}, {dr['style_line']}, {CFG['policy']['image_text']}"), cap)

    def test_prompt_is_cleaned_of_hex_codes_and_shot_labels(self):
        out = director.image_prompt({**SCENE, "colors": "pure white (#FFFFFF) rays, sky blue (#87CEEB)", "setting": "Shot 7: Wide landscape shot"})
        self.assertNotIn("#", out); self.assertNotIn("Shot 7", out); self.assertIn("pure white rays", out)



if __name__ == "__main__":
    unittest.main()
