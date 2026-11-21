"""The picture description under the hard cap: priorities, whole-item dropping, the user's own details first, and the cap always holds."""
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from img_video import comfy, compose, config, director, llm, pipeline
from img_video.jobs import Job

CFG, CAPS = config.load()
ANN = {"label": "Ann (left in reference image 1)", "outfit": "red dress, red tights, black boots, black leather gloves"}
BO = {"label": "Bo (right in reference image 1)", "outfit": "khaki cargo pants, white shirt, dark shoes"}
STYLE = [("look", "cinematic photo"), ("palette", "warm gold and red"), ("lighting", "soft sunset light"), ("camera", "eye-level")]
REF = "Only the people come from the references."


def run(cap, people=(ANN, BO), stated=(), subject="They walk hand in hand", setting=("Paris street", "wide shot"), colors="gold, red", style=STYLE, clause=72, fix=None):
    return compose.compose(list(people), subject, list(setting), colors, list(style), cap, clause, REF, stated, fix)


class ComposeTests(unittest.TestCase):
    def test_when_everything_fits_nothing_is_left_out_and_the_format_is_stable(self):
        r = run(1000)
        self.assertEqual(r["dropped"], []); self.assertFalse(r["fixed"])
        self.assertEqual(r["prompt"], "Ann (left in reference image 1): red dress, red tights, black boots, black leather gloves. Bo (right in reference image 1): khaki cargo pants, white shirt, dark shoes. "
                                      "Only the people come from the references. They walk hand in hand. Setting: Paris street, wide shot. Colors: gold, red.")
        self.assertEqual(r["style"], "cinematic photo, warm gold and red, soft sunset light, eye-level")

    def test_the_least_valuable_whole_facts_go_first_and_nothing_is_cut_in_the_middle(self):
        full = run(1000); need = full["length"]
        seen = []
        for cap in range(need, 150, -7):
            r = run(cap); self.assertLessEqual(r["length"], cap if not r["fixed"] else 10 ** 6)
            seen.append((cap, r["dropped"]))
            for item in ("red dress", "black boots", "khaki cargo pants", "white shirt"): self.assertTrue(item in r["prompt"] or item in r["dropped"], (cap, item))      # an item is whole or absent, never half
        order = []
        for _cap, dropped in seen:
            for d in dropped:
                if d not in order: order.append(d)
        self.assertEqual(order[:3], ["gold, red", "eye-level", "soft sunset light"])                                    # colors, then the style's camera and lighting go before anything else
        self.assertLess(order.index("warm gold and red"), order.index("wide shot")); self.assertLess(order.index("wide shot"), order.index("cinematic photo"))

    def test_what_the_user_stated_stays_and_the_directors_own_details_go_first(self):
        stated = ["black boots", "red dress", "khaki cargo pants", "white shirt"]
        r = run(300, stated=stated)
        for item in ("red dress", "black boots", "khaki cargo pants", "white shirt"): self.assertIn(item, r["prompt"])
        self.assertTrue({"red tights", "black leather gloves", "dark shoes"} & set(r["dropped"]))                       # not stated: dropped before anything stated
        none = run(300); self.assertNotIn("black boots", none["dropped"][:1])
        self.assertLessEqual(r["length"], 300)

    def test_the_place_is_kept_and_framing_goes_first(self):
        r = run(230, setting=("Paris streets", "low angle", "shallow depth of field"), style=[("look", "photo")], colors="")
        self.assertIn("Paris streets", r["prompt"]); self.assertLessEqual(r["length"], 230)
        self.assertIn("shallow depth of field", r["dropped"])

    def test_when_the_musts_alone_do_not_fit_the_model_rewrites_them_and_a_bad_answer_is_ignored(self):
        calls = []
        def good(text, room): calls.append(room); return "Ann (left in reference image 1): red dress. Bo (right in reference image 1): white shirt. They walk."
        r = run(150, stated=["red dress", "black boots", "khaki cargo pants", "white shirt"], fix=good)
        self.assertTrue(r["fixed"]); self.assertEqual(len(calls), 1); self.assertLessEqual(r["length"], 150); self.assertTrue(r["prompt"].startswith("Ann (left in reference image 1)"))
        def bad(text, room): return "no tags here and also much too long " * 10
        r = run(150, stated=["red dress", "black boots", "khaki cargo pants", "white shirt"], fix=bad); self.assertLessEqual(r["length"], 150)               # ignored: the word-boundary cut keeps the cap
        def boom(text, room): raise RuntimeError("no model")
        r = run(150, stated=["red dress", "black boots", "khaki cargo pants", "white shirt"], fix=boom); self.assertLessEqual(r["length"], 150)
        r = run(150, stated=["red dress", "black boots", "khaki cargo pants", "white shirt"]); self.assertLessEqual(r["length"], 150); self.assertNotRegex(r["prompt"], r"\s(in|with|the|of|and)$")

    def test_a_style_detail_the_user_stated_survives_while_the_directors_own_style_goes(self):
        style = [("look", "cinematic photo"), ("palette", "warm golds, deep reds"), ("lighting", "backlit golden hour glow"), ("camera", "full body shots, shallow depth of field")]
        stated = ["both of them in full body shots throughout"]; need = run(1000, style=style, stated=stated)["length"]; hit = False
        for cap in range(need - 3, 140, -3):
            r = run(cap, style=style, stated=stated); self.assertLessEqual(r["length"], cap)
            if "shallow depth of field" in r["dropped"]:                                                                         # the director's own neighbour in the same style part went...
                self.assertIn("full body shots", r["style"]); hit = True; break                                                    # ...while the user's "full body shots" stayed
        self.assertTrue(hit)

    def test_function_words_do_not_make_two_phrases_the_same_thing(self):
        self.assertEqual(compose.words("The man in a white shirt, of course"), {"man", "white", "shirt", "course"})
        self.assertFalse(compose.words("shallow depth of field") & compose.words("both of them in full body shots"))
        self.assertTrue(compose.words("red dress") & compose.words("the woman wears a red dress"))

    def test_outfits_are_cut_by_whole_items(self):
        text = "Long black hair, red dress, red tights, black boots, black leather gloves"
        self.assertEqual(compose.cut_items(text, 60), "Long black hair, red dress, red tights, black boots"); self.assertEqual(compose.cut_items(text, 200), text)
        self.assertEqual(compose.cut_items(text, 20), "Long black hair"); self.assertEqual(compose.cut_items("one very long first item", 12), "one very")        # the first item stays, cut at a word boundary
        self.assertEqual(compose.cut_items("", 10), "")

    def test_the_cap_always_holds_for_random_facts(self):
        rnd = random.Random(7); vocab = "red blue black white green khaki leather wool cotton silk dress shirt pants boots jacket scarf hat gloves coat shoes tights".split()
        for _ in range(300):
            def phrase(): return " ".join(rnd.choice(vocab) for _ in range(rnd.randint(1, 3)))
            people = [{"label": f"P{i} (reference image {i})", "outfit": ", ".join(phrase() for _ in range(rnd.randint(0, 5)))} for i in range(rnd.randint(0, 3))]
            stated = [phrase() for _ in range(rnd.randint(0, 4))]; cap = rnd.randint(120, 520); style = [(n, phrase()) for n in ("look", "palette", "lighting", "camera") if rnd.random() < .8]
            r = compose.compose(people, phrase(), [phrase() for _ in range(rnd.randint(1, 3))], phrase() if rnd.random() < .7 else "", style, cap, rnd.choice([0, 72]), REF if people else "", stated)
            self.assertLessEqual(r["length"], cap, (cap, r))
            musts = []
            for pe in people:
                for it in compose.items_of(pe["outfit"]):
                    if compose.words(it) & set().union(*[compose.words(s) for s in stated] or [set()]): musts.append(it)
            if not r["fixed"]:
                for m in musts: self.assertIn(m, r["prompt"])                                                          # a stated item is never dropped unless the musts alone cannot fit


class FixedSubjectTests(unittest.TestCase):
    def test_a_fixed_subject_keeps_every_item_and_the_scene_gives_way_instead(self):
        fixed = dict(ANN, fixed=True)
        r = run(240, people=(fixed,), setting=("Paris street", "wide shot, low angle, golden hour backlight"), colors="amber sky, grey stones")
        self.assertTrue(all(it in r["prompt"] for it in compose.items_of(ANN["outfit"])), r["prompt"])                         # nothing of the subject is dropped
        self.assertFalse(any(d in compose.items_of(ANN["outfit"]) for d in r["dropped"]))
        loose = run(240, people=(ANN,), setting=("Paris street", "wide shot, low angle, golden hour backlight"), colors="amber sky, grey stones")
        self.assertNotEqual(r["dropped"], loose["dropped"])                                                                     # without "fixed" the old order applies


class DirectorComposeTests(unittest.TestCase):
    def test_stated_and_place_are_read_from_the_analysis_and_every_picture_says_where_it_is(self):
        def fake(c, system, user, temperature=0.6, max_tokens=4000, check=None, attempts=3):
            if "before anything is drawn. First" in system:
                o = {"kind": "story", "intent": "i", "audience": "a", "stated": ["white shirt", "khaki pants", "red dress", "black boots", 7], "place": "Paris streets",
                     "characters": [{"id": "a", "name": "Ann", "origin": "named", "role": "r"}, {"id": "b", "name": "Bo", "origin": "named", "role": "r"}], "rules": ["r"], "open_details": ["d"], "title": "T",
                     "shot_list": [{"topic": "t1", "purpose": "p", "characters": ["a", "b"]}, {"topic": "t2", "purpose": "p", "characters": []}]}
            elif "fixing every open detail" in system:
                o = {"decisions": [{"detail": "d", "value": "v"}], "style": {"look": "cinematic photo", "palette": "warm gold", "lighting": "sunset", "camera": "eye-level"},
                     "cast": [{"id": "a", "appearance": "red dress, black boots, black leather gloves"}, {"id": "b", "appearance": "white shirt, khaki pants, dark shoes"}], "recurring": []}
            elif "shorten text" in system: o = {k: "short phrase" for k in director.SCENE}
            else: o = {"rules_applied": "r", "scene": {"subject": "They stroll hand in hand", "setting": "cobblestone street, wide shot", "colors": "gold, red"}, "caption": "c", "motion": "pan", "narration": "line"}
            if check:
                err = check(o)
                if err and "every shot must show" in err: err = check(o)                      # the model keeps its answer; the check asks only once
                assert err is None, err
            return o
        with tempfile.TemporaryDirectory() as d, mock.patch.object(llm, "ask_json", fake):
            (Path(d) / "jobs").mkdir(); job = Job.create(Path(d) / "jobs", {"query": "q", "count": 2, "aspect": "16:9", "video": True}); logs = []; job.log = logs.append
            job.write("plan.json", {"count": 2, "needs_web": False, "research_questions": [], "tone": "t", "narrated": True}); job.write("research.json", [])
            director.direct(job, CFG, CAPS); an = job.read("director/01_analyze.json"); it = job.read("items.json"); dr = job.read("direction.json")
        self.assertEqual(an["stated"], ["white shirt", "khaki pants", "red dress", "black boots"]); self.assertEqual(an["place"], "Paris streets")           # a non-text entry is ignored
        p1 = it["items"][0]["image_prompt"]; self.assertIn("Paris streets", p1); self.assertIn("Setting: Paris streets, cobblestone street", p1)                       # the place was not in the shot's setting: it is added in front
        for item in ("red dress", "black boots", "white shirt", "khaki pants"): self.assertIn(item, p1)
        self.assertEqual(len(p1.rstrip(". ")) + 2 + len(it["items"][0].get("style", dr["style_line"])) + 2 + len(CFG["policy"].get("image_text", "")) <= CFG["limits"]["image_prompt_chars"], True)
        self.assertEqual(it["items"][1]["characters"], ["a"]); self.assertIn("style", it["items"][1])                                                                   # a shot the model left empty shows the lead too

    def test_the_photo_whose_clothes_match_the_planned_outfit_is_preferred(self):
        cast = [{"id": "a", "name": "Ann", "photo": True, "photos": [1, 2], "pointers": {}, "appearance": "white shirt, khaki pants", "looks": {1: "grey hoodie, jeans", 2: "white shirt, tan pants"}}]
        self.assertEqual([director.select_refs(cast, ["a"], k)[0] for k in (1, 2, 3)], [[2], [2], [2]])                       # photo 2 shows the planned clothes: always chosen
        cast[0]["looks"] = {1: "white shirt", 2: "white shirt"}; self.assertEqual([director.select_refs(cast, ["a"], k)[0] for k in (1, 2)], [[1], [2]])        # equal: rotate as before


class PictureStyleTests(unittest.TestCase):
    def test_a_picture_can_carry_its_own_style_and_an_empty_one_leaves_no_stray_comma(self):
        seen = []
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "jobs").mkdir(); job = Job.create(Path(d) / "jobs", {"query": "q", "count": 3, "aspect": "1:1"}); job.write("plan.json", {"count": 3, "needs_web": False, "research_questions": [], "tone": "t"})
            items = [{"topic": "a", "caption": "c", "image_prompt": "p1."}, {"topic": "b", "caption": "c", "image_prompt": "p2", "style": "short style"}, {"topic": "c", "caption": "c", "image_prompt": "p3", "style": ""}]
            src = type("S", (), {"style": "GLOBAL", "items": lambda self: enumerate(items, 1)})(); clause = CFG["policy"].get("image_text", "")
            with mock.patch.object(comfy, "preflight"), mock.patch.object(comfy, "wait_until_free"), mock.patch.object(comfy, "generate_image", side_effect=lambda base, c, prompt, w, h, seed, **kw: seen.append(prompt) or (b"PNG", 0.1)):
                pipeline._images(job, CFG, CAPS, src)
        self.assertEqual(seen, [f"p1, GLOBAL, {clause}", f"p2, short style, {clause}", f"p3, {clause}"])


if __name__ == "__main__":
    unittest.main()
