"""Characters in the director: who is in the pictures is decided once, described once, and the same words go into every picture prompt that shows them."""
import tempfile
import unittest
from unittest import mock

from img_video import config, director, llm
from img_video.jobs import Job

CFG, CAPS = config.load()
HARRY = "lanky teen, round glasses, messy black hair, scarlet-and-gold scarf, black school robes"
GINNY = "freckled teen girl, long red hair, green jacket, silver wand"
HARRY2 = "lanky teen, round glasses, black hair, scarlet scarf"      # what fits when two characters share a shot (about 60 characters)
GINNY2 = "freckled girl, long red hair, green jacket"
SCENE = {"subject": "Harry walks down a torch-lit corridor, facing the camera", "setting": "Hogwarts stone corridor, low angle", "colors": "warm torch orange, deep blue shadows"}


def make_fake(characters, shot_chars, seen=None, appearance=None):
    short = len(characters) > 1
    cast = [{"id": c["id"], "appearance": (appearance or {}).get(c["id"], (HARRY2 if short else HARRY) if c["id"] == "harry" else (GINNY2 if short else GINNY))} for c in characters]
    def fake(c, system, user, temperature=0.6, max_tokens=4000, check=None, attempts=3):
        if seen is not None: seen.append((system, user))
        if "before anything is drawn. First" in system:
            o = {"kind": "story", "intent": "i", "audience": "a", "characters": characters, "rules": ["r"], "open_details": ["d"], "title": "T", "narration_voice": "Harry, in the first person",
                 "shot_list": [{"topic": f"t{i}", "purpose": "p", "characters": shot_chars[i - 1]} for i in range(1, len(shot_chars) + 1)]}
        elif "fixing every open detail" in system:
            o = {"decisions": [{"detail": "d", "value": "v"}], "style": {"look": "anime", "palette": "warm", "lighting": "torchlight", "camera": "wide"}, "cast": cast, "recurring": []}
        elif "shorten text" in system:
            o = {k: "short phrase" for k in director.SCENE}
        else:
            o = {"rules_applied": "r", "scene": dict(SCENE), "caption": "cap", "motion": "slow pan", "narration": "short line"}
        if check:
            err = check(o)
            if err and "every shot must show" in err: err = check(o)                      # the model keeps its answer; the check asks only once
            assert err is None, err
        return o
    return fake


def run_direct(characters, shot_chars, **kw):
    seen = []
    with tempfile.TemporaryDirectory() as d, mock.patch.object(llm, "ask_json", make_fake(characters, shot_chars, seen, **kw)):
        n = len(shot_chars); job = Job.create(d, {"query": "q", "count": n, "aspect": "16:9", "video": True})
        job.write("plan.json", {"count": n, "needs_web": False, "research_questions": [], "tone": "mysterious", "narrated": True}); job.write("research.json", [])
        director.direct(job, CFG, CAPS)
        return job.read("direction.json"), job.read("items.json"), seen


ONE = [{"id": "harry", "name": "Harry", "origin": "named", "role": "the lead", "main": True}]
TWO = ONE + [{"id": "ginny", "name": "Ginny", "origin": "implied", "role": "his girlfriend", "main": False}]


class CastTests(unittest.TestCase):
    def test_normalizing_the_models_answer(self):
        an = director._norm_cast({"characters": [{"name": "Harry Potter"}, "Ron", {"id": "harry_potter", "name": "dup"}, 7], "kind": "weird",
                                  "shot_list": [{"characters": ["harry_potter", "ghost", "ron"]}, {"characters": "x"}, {}]}, 3)
        self.assertEqual([c["id"] for c in an["characters"]], ["harry_potter", "ron"]); self.assertTrue(an["characters"][0]["main"]); self.assertEqual(an["kind"], "explainer")
        self.assertEqual([s["characters"] for s in an["shot_list"]], [["harry_potter", "ron"], ["harry_potter"], ["harry_potter"]])      # an empty shot gets the lead
        self.assertEqual(an["narration_voice"], "a neutral narrator")
        none = director._norm_cast({"shot_list": [{"characters": ["x"]}]}, 1); self.assertEqual((none["characters"], none["shot_list"][0]["characters"]), ([], []))

    def test_the_appearance_budget_shrinks_with_the_characters_that_share_a_shot(self):
        one = director.char_cap(CFG, {"shot_list": [{"characters": ["a"]}]}); two = director.char_cap(CFG, {"shot_list": [{"characters": ["a", "b"]}]}); three = director.char_cap(CFG, {"shot_list": [{"characters": list("abc")}]}); four = director.char_cap(CFG, {"shot_list": [{"characters": list("abcd")}]})
        self.assertEqual(one, director.CHAR_CAP); self.assertLessEqual(two, one); self.assertLessEqual(three, two); self.assertLess(four, one); self.assertGreaterEqual(four, 40)      # with the short no-text clause two characters still get the full cap

    def test_cast_line_uses_the_cast_sheet_words_and_shortens_evenly_to_fit(self):
        cast = [{"id": "harry", "name": "Harry", "appearance": HARRY}, {"id": "ginny", "name": "Ginny", "appearance": GINNY}]
        self.assertEqual(director.cast_line(cast, ["harry"], 300), f"Harry: {HARRY}."); self.assertEqual(director.cast_line(cast, [], 300), "")
        both = director.cast_line(cast, ["harry", "ginny"], 100); self.assertLessEqual(len(both), 100); self.assertTrue(both.startswith("Harry: ") and "Ginny: " in both)
        self.assertEqual(director.cast_line(cast, ["ginny", "harry"], 400), f"Ginny: {GINNY}. Harry: {HARRY}.")

    def test_every_picture_that_shows_a_character_carries_the_same_words_and_the_prompt_fits(self):
        dr, it, _ = run_direct(TWO, [["harry"], ["harry", "ginny"], [], ["harry"], ["harry", "ginny"]])
        self.assertEqual([c["name"] for c in dr["cast"]], ["Harry", "Ginny"]); self.assertEqual(it["cast"][0]["appearance"], HARRY2)
        for x, ids in zip(it["items"], [["harry"], ["harry", "ginny"], ["harry"], ["harry"], ["harry", "ginny"]]):                          # the empty third shot got the lead
            self.assertEqual(x.get("characters"), ids)
            self.assertEqual("Harry: " in x["image_prompt"], "harry" in ids); self.assertEqual("Ginny: " in x["image_prompt"], "ginny" in ids)
            if ids: self.assertTrue(x["image_prompt"].startswith(("Harry: ", "Ginny: ")))
            total = len(x["image_prompt"]) + 2 + len(dr["style_line"]) + 2 + len(CFG["policy"].get("image_text", "")) + 2
            self.assertLessEqual(total, CFG["limits"]["image_prompt_chars"], x["image_prompt"])
        solo = [x["image_prompt"].split(" Setting:")[0] for x in it["items"] if x.get("characters") == ["harry"]]; self.assertEqual(len({s.split(".")[0] for s in solo}), 1)      # same words for Harry in both solo shots
        self.assertEqual(dr["kind"], "story"); self.assertEqual(dr["narration_voice"], "Harry, in the first person")

    def test_a_single_character_gets_the_full_appearance_line(self):
        _, it, _ = run_direct(ONE, [["harry"]] * 3); self.assertTrue(all(x["image_prompt"].startswith(f"Harry: {HARRY}.") for x in it["items"]))

    def test_no_characters_leaves_the_prompts_exactly_as_before(self):
        dr, it, _ = run_direct([], [[], [], []])
        self.assertEqual(dr["cast"], []); self.assertEqual(it["cast"], [])
        for x in it["items"]: self.assertEqual(x["image_prompt"], director.image_prompt(SCENE)); self.assertNotIn("characters", x)

    def test_the_shot_writer_is_told_who_is_in_the_shot_the_voice_and_the_smaller_budget(self):
        _, _, seen = run_direct(TWO, [["harry", "ginny"], [], ["harry"]])
        shot_prompts = [u for s, u in seen if "ONE shot" in s]
        self.assertIn("Characters in this shot: Harry, Ginny", shot_prompts[0]); self.assertIn("Characters in this shot: Harry.", shot_prompts[1]); self.assertIn("spoken by Harry, in the first person", shot_prompts[0])
        self.assertIn("continues the story", shot_prompts[0]); self.assertIn("[Harry, Ginny]", shot_prompts[1])                          # the earlier shots are listed with who was in them
        limit = lambda p: int(p.split("subject ")[1].split(",")[0]); self.assertLess(limit(shot_prompts[0]), limit(shot_prompts[1]))      # two characters leave less room for the subject than none

    def test_decide_asks_again_when_a_character_is_missing_or_far_too_long_and_trims_the_rest(self):
        an = {"characters": director._norm_cast({"characters": TWO, "shot_list": [{"characters": ["harry", "ginny"]}]}, 1)["characters"], "shot_list": [{"characters": ["harry", "ginny"]}], "kind": "story", "intent": "i", "rules": [], "open_details": []}
        calls = []
        def ask(c, system, user, temperature=0.6, max_tokens=4000, check=None, attempts=3):
            good = {"decisions": [{"detail": "d", "value": "v"}], "style": {"look": "anime", "palette": "warm", "lighting": "torch", "camera": "wide"}, "recurring": []}
            tries = [dict(good, cast=[{"id": "harry", "appearance": HARRY2}]),                                                                             # ginny is missing
                     dict(good, cast=[{"id": "harry", "appearance": "x " * 200}, {"id": "ginny", "appearance": GINNY2}]),                                     # far too long
                     dict(good, cast=[{"id": "harry", "appearance": HARRY2}, {"id": "ginny", "appearance": GINNY2}])]
            for o in tries:
                msg = check(o); calls.append(msg)
                if msg is None: return o
        with mock.patch.object(llm, "ask_json", ask):
            dec = director.decide(CFG, {"query": "q"}, {"tone": "t"}, an, [], None)
        self.assertIn("EVERY character", calls[0]); self.assertIn("at most", calls[1]); self.assertIsNone(calls[2])
        cc = director.char_cap(CFG, an); self.assertTrue(all(len(c["appearance"]) <= cc for c in dec["cast"]))                                          # long ones are trimmed to the budget
        self.assertEqual([c["id"] for c in dec["cast"]], ["harry", "ginny"])


if __name__ == "__main__":
    unittest.main()


class TrimTests(unittest.TestCase):
    def test_trimming_cuts_each_field_to_its_own_limit_first_and_never_ends_on_a_dangling_word(self):
        scene = {"subject": "Harry stands motionless in the vast echoing hall, breath visible, lips moving silently", "setting": "Low angle wide shot of a vast empty stone hall with flickering torches along the walls",
                 "colors": "Desaturated greys, midnight blues, charcoal blacks, warm amber fireglow from the torches"}
        lim = {"subject": 82, "setting": 41, "colors": 41}; cap = 190
        cut = director._trim_longest(scene, director.SCENE, lambda sc: len(director.image_prompt(sc).rstrip(". ")), cap, lim=lim)
        self.assertLessEqual(len(director.image_prompt(cut).rstrip(". ")), cap)
        self.assertTrue(scene["subject"].startswith(cut["subject"]) and len(cut["subject"]) >= 70)  # the subject only lost what was over ITS limit (one word), it was not cut to the floor
        self.assertLessEqual(len(cut["setting"]), 41); self.assertLessEqual(len(cut["colors"]), 41)
        for v in cut.values(): self.assertNotRegex(v, r"\s(in|with|the|of|and|a|from|to)$")
        self.assertEqual(director._cut_phrase("Harry stands motionless in the hall", 26), "Harry stands motionless")
        self.assertEqual(director._cut_phrase("alpha beta gamma delta", 12), "alpha beta")        # same as guard.cut when nothing dangles
