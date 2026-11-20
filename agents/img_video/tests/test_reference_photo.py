"""The main character as a photo: the job keeps the photo, the director casts that person without describing them, pictures that show them carry the reference, nothing else changes."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from img_video import comfy, config, director, guard, llm, pipeline
from img_video.jobs import Job

CFG, CAPS = config.load()
OUTFIT = "navy trench coat, red beret"
SCENE = {"subject": "The person strolls along a rainy cobblestone street, facing the camera", "setting": "Paris street, wide shot", "colors": "grey rain, warm cafe light"}


def photo(d, name="me.jpg", size=300): p = Path(d) / name; p.write_bytes(b"\xff\xd8" + bytes(size)); return p


class JobTests(unittest.TestCase):
    def test_the_photos_are_copied_into_the_job_and_named_in_the_request(self):
        with tempfile.TemporaryDirectory() as d:
            job = Job.create(Path(d) / "jobs", {"query": "q", "aspect": "1:1"}) if (Path(d) / "jobs").mkdir() is None else None
            names = job.add_references([photo(d, "a.jpg"), (photo(d, "b.PNG"), "my wife"), photo(d, "c.webp")] + [photo(d, f"x{k}.jpg") for k in range(5)])
            self.assertEqual(names, ["reference/ref1.jpg", "reference/ref2.png", "reference/ref3.webp", "reference/ref4.jpg", "reference/ref5.jpg", "reference/ref6.jpg"])      # six at most, extension kept
            self.assertEqual(job.state["request"]["reference_who"][:3], ["", "my wife", ""])                                   # what the user called each photo
            self.assertEqual(job.state["request"]["references"], names); self.assertTrue(all(p.is_file() for p in job.reference_paths()))
            self.assertEqual(Job.load(Path(d) / "jobs", job.id).state["request"]["references"], names)                       # persisted: a resume sees them
            self.assertEqual(len(job.reference_hashes()), 6); self.assertEqual(oct(job.reference_paths()[0].stat().st_mode & 0o777), "0o600")

    def test_unsuitable_files_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "jobs").mkdir(); job = Job.create(Path(d) / "jobs", {"query": "q", "aspect": "1:1"}); (Path(d) / "x.txt").write_text("hi")
            for bad in (Path(d) / "x.txt", Path(d) / "missing.jpg"):
                with self.assertRaises(ValueError): job.add_references([bad])
            with mock.patch.object(Job, "MAX_PHOTO_BYTES", 100), self.assertRaises(ValueError): job.add_references([photo(d, size=500)])


class PictureStageTests(unittest.TestCase):
    def run_images(self, items, backend="qwen-image-21", local=False):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "jobs").mkdir(); job = Job.create(Path(d) / "jobs", {"query": "q", "count": len(items), "aspect": "1:1"}); job.add_references([photo(d, "a.jpg"), photo(d, "b.png")])
            job.write("plan.json", {"count": len(items), "needs_web": False, "research_questions": [], "tone": "t"})
            cfg = {**CFG, "comfy": {**CFG["comfy"], "backend": backend}, "image": {**CFG["image"], "backend": "qwen-image-local" if local else "comfy"}}
            calls, uploads = [], []
            def gen(base, c, prompt, w, h, seed, **kw): calls.append(kw); return b"PNG", 0.1
            src = type("S", (), {"style": "STYLE", "items": lambda self: enumerate(items, 1)})()
            with mock.patch.object(comfy, "preflight"), mock.patch.object(comfy, "wait_until_free"), mock.patch.object(comfy, "generate_image", side_effect=gen), \
                 mock.patch.object(comfy, "upload", side_effect=lambda base, data, name: uploads.append(name) or name):
                pipeline._images(job, cfg, CAPS, src); return calls, uploads, job

    def test_the_photos_are_uploaded_once_and_only_pictures_with_the_person_get_them(self):
        calls, uploads, job = self.run_images([{"topic": "a", "caption": "c", "image_prompt": "p1", "refs": [1, 2]}, {"topic": "b", "caption": "c", "image_prompt": "p2"}, {"topic": "c", "caption": "c", "image_prompt": "p3", "refs": [2]}])
        self.assertEqual(len(uploads), 2); self.assertTrue(all(n.startswith("ref_") for n in uploads))                       # two photos, once for the whole job
        self.assertEqual([c.get("refs") for c in calls], [uploads, None, [uploads[1]]])                                      # each picture gets only the photos of the people in it

    def test_a_set_without_the_person_uploads_nothing_and_reference_photos_need_the_qwen_backend(self):
        calls, uploads, _ = self.run_images([{"topic": "a", "caption": "c", "image_prompt": "p1"}]); self.assertEqual((uploads, calls), ([], [{}]))
        with self.assertRaises(comfy.ComfyError): self.run_images([{"topic": "a", "caption": "c", "image_prompt": "p1", "refs": [1]}], backend="flux2-klein")


class WorkflowTests(unittest.TestCase):
    def test_the_reference_graph_has_loaders_the_images_inputs_and_the_vae(self):
        g = comfy.qwen21_workflow("p", 640, 360, 1, CFG["comfy"], refs=["a.png", "b.png"]); enc = g["4"]["inputs"]
        self.assertEqual((enc["images.image_1"], enc["images.image_2"], enc["vae"]), (["301", 0], ["302", 0], ["3", 0])); self.assertEqual(g["301"], {"class_type": "LoadImage", "inputs": {"image": "a.png"}})
        plain = comfy.qwen21_workflow("p", 640, 360, 1, CFG["comfy"]); self.assertNotIn("vae", plain["4"]["inputs"]); self.assertFalse(any(k.startswith("images.") for k in plain["4"]["inputs"]))



COUPLE = [{"id": "hus", "name": "the husband", "origin": "photo", "role": "husband", "photos": [1]}, {"id": "wife", "name": "the wife", "origin": "photo", "role": "wife", "photos": [2]}]


import json as _json


def subs(*items):
    """The vision model's answer for one photo: items are (at, look)."""
    return _json.dumps({"subjects": [{"at": a, "look": l} for a, l in items]})


COUPLE = subs(("left", "bearded man, white shirt"), ("right", "long dark hair, red dress"))
SOLO = subs(("only", "short grey hair, glasses"))
NOBODY = subs()


seen_ask = []


def make_llm(characters, shot_chars, seen=None, appearances=None):
    cast = [{"id": c["id"], "appearance": (appearances or {}).get(c["id"], f"outfit of {c['id']}")} for c in characters]
    def fake(c, system, user, temperature=0.6, max_tokens=4000, check=None, attempts=3):
        if seen is not None: seen.append((system, user))
        if "before anything is drawn. First" in system:
            o = {"kind": "story", "intent": "i", "audience": "a", "characters": characters, "rules": ["r"], "open_details": ["d"], "title": "T",
                 "shot_list": [{"topic": f"t{i}", "purpose": "p", "characters": ids} for i, ids in enumerate(shot_chars, 1)]}
        elif "fixing every open detail" in system:
            o = {"decisions": [{"detail": "d", "value": "v"}], "style": {"look": "photo", "palette": "warm", "lighting": "dusk", "camera": "wide"}, "cast": cast, "recurring": []}
        elif "shorten text" in system: o = {k: "short phrase" for k in director.SCENE}
        else: o = {"rules_applied": "r", "scene": dict(SCENE), "caption": "cap", "motion": "pan", "narration": "line"}
        if check:
            err = check(o)
            if err and "every shot must show" in err: seen_ask.append(err); err = check(o)                      # the model keeps its answer; the check asks only once
            assert err is None, err
        return o
    return fake


def run_direct(photo_answers, characters, shot_chars, seen=None, who=None):
    """Runs the director on a job with one photo per answer; returns (direction, items, job log lines)."""
    logs = []
    with tempfile.TemporaryDirectory() as d, mock.patch.object(llm, "ask_json", make_llm(characters, shot_chars, seen)), mock.patch.object(llm, "ask_about_image", side_effect=list(photo_answers)):
        (Path(d) / "jobs").mkdir(); job = Job.create(Path(d) / "jobs", {"query": "q", "count": len(shot_chars), "aspect": "16:9", "video": True}); job.log = logs.append
        job.add_references([(photo(d, f"p{k}.jpg"), (who or [""] * 9)[k - 1]) for k in range(1, len(photo_answers) + 1)])
        job.write("plan.json", {"count": len(shot_chars), "needs_web": False, "research_questions": [], "tone": "t", "narrated": True}); job.write("research.json", [])
        director.direct(job, CFG, CAPS); return job.read("direction.json"), job.read("items.json"), logs


class PhotoSubjectsTests(unittest.TestCase):
    def test_the_vision_answer_is_parsed_leniently_and_a_photo_that_cannot_be_read_counts_as_one_person(self):
        self.assertEqual(director._parse_subjects('Sure! ' + COUPLE + ' hope that helps'), [{"at": "left", "look": "bearded man, white shirt"}, {"at": "right", "look": "long dark hair, red dress"}])
        self.assertEqual(director._parse_subjects(NOBODY), []); self.assertIsNone(director._parse_subjects("no json here")); self.assertIsNone(director._parse_subjects('{"subjects": "x"}'))
        self.assertEqual(director._parse_subjects(subs(("middle", "x")))[0]["at"], "")                                   # an unknown place is dropped, the subject stays
        with tempfile.TemporaryDirectory() as d, mock.patch.object(llm, "ask_about_image", side_effect=["garbage", RuntimeError("no vision"), NOBODY, COUPLE]) as look:
            (Path(d) / "jobs").mkdir(); job = Job.create(Path(d) / "jobs", {"query": "q", "aspect": "1:1"}); job.add_references([photo(d, f"{k}.jpg") for k in range(4)])
            got = director.describe_photos(job, CFG)
            self.assertEqual([len(x) for x in got], [1, 1, 0, 2]); self.assertEqual(got[0][0]["at"], "only")                # unreadable: assumed one person; nobody in the photo: none
            director.describe_photos(job, CFG); self.assertEqual(look.call_count, 4)                                       # cached

    def test_the_brief_is_short_and_lists_the_ids(self):
        text = director.photo_brief({"references": ["a", "b"], "reference_who": ["", "me"]}, [json_subs(COUPLE), json_subs(NOBODY)])
        self.assertIn("1.1 left: bearded man, white shirt; 1.2 right: long dark hair, red dress", text); self.assertIn('Photo 2 (the user calls it "me"): no one', text); self.assertLess(len(text), 800)
        self.assertEqual(director.photo_brief({}, []), "")


def json_subs(text): return director._parse_subjects(text)


CAR = _json.dumps({"subjects": [{"at": "only", "kind": "object", "what": "red sports car", "look": "red two-door coupe, black roof, chrome wheels"}]})


class ThingPhotoTests(unittest.TestCase):
    def test_the_vision_answer_keeps_kind_and_noun_only_for_things_and_a_person_stays_as_before(self):
        got = director._parse_subjects(CAR); self.assertEqual(got, [{"at": "only", "look": "red two-door coupe, black roof, chrome wheels", "kind": "object", "what": "red sports car"}])
        self.assertNotIn("kind", director._parse_subjects(COUPLE)[0])                                              # persons: exactly the old shape (and old caches stay valid)
        self.assertEqual(director._parse_subjects(subs(("only", "x")))[0], {"at": "only", "look": "x"})

    def test_the_question_carries_the_request_and_the_brief_names_things(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(llm, "ask_about_image", side_effect=[CAR]) as look:
            (Path(d) / "jobs").mkdir(); job = Job.create(Path(d) / "jobs", {"query": "my car in Paris", "aspect": "1:1"}); job.add_references([photo(d, "c.jpg")])
            got = director.describe_photos(job, CFG, "my car in Paris"); self.assertEqual(got[0][0]["kind"], "object"); self.assertIn("my car in Paris", look.call_args[0][2])
        text = director.photo_brief({"references": ["a"]}, [json_subs(CAR)]); self.assertIn("1.1 only: red sports car, red two-door coupe", text); self.assertIn("A thing (animal or object)", text)
        self.assertNotIn("A thing", director.photo_brief({"references": ["a"]}, [json_subs(COUPLE)]))                # people only: the brief is the old one

    def test_a_car_photo_runs_through_the_director_with_its_own_clause_and_label(self):
        chars = [{"id": "car", "name": "the red car", "origin": "named", "role": "hero", "main": True, "in": ["1.1"]}]
        dr, it, logs = run_direct([CAR], chars, [["car"], ["car"], []])
        c = dr["cast"][0]; self.assertEqual((c["kind"], c["what"], c["photo"]), ("object", "red sports car", True)); self.assertIn("red two-door coupe", c["appearance"])      # words come from the photo
        p = it["items"][0]["image_prompt"]; self.assertIn("Red car (reference image 1)", p); self.assertIn("Only the red sports car comes from the references.", p); self.assertNotIn("people", p)
        self.assertEqual(it["items"][0]["refs"], [1]); self.assertNotIn("refs", it["items"][2]); self.assertTrue(all(len(x["image_prompt"]) <= 500 for x in it["items"]))

    def test_the_clause_names_what_the_photos_give(self):
        person = {"id": "a", "name": "A", "photo": True, "photos": [1]}; car = {"id": "c", "name": "car", "photo": True, "photos": [2], "kind": "object", "what": "Blue Van"}; dog = {"id": "d", "name": "d", "photo": True, "photos": [3], "kind": "animal", "what": "dog"}
        self.assertEqual(director.ref_clause([person], ["a"]), director.REF_CLAUSE); self.assertEqual(director.ref_clause([person, car], ["c"]), "Only the blue van comes from the references.")
        self.assertEqual(director.ref_clause([person, car, dog], ["a", "c", "d"]), "Only the people and blue van and dog come from the references."); self.assertEqual(director.ref_clause([person], []), "")


class EverySubjectShotTests(unittest.TestCase):
    CAR_CHARS = [{"id": "car", "name": "the red car", "origin": "named", "role": "hero", "main": True, "in": ["1.1"]}]

    def test_a_shot_without_the_subject_is_asked_about_once_and_then_stands(self):
        seen_ask.clear(); run_direct([CAR], self.CAR_CHARS, [[], ["car"], ["car"]])
        self.assertEqual(len(seen_ask), 1); self.assertIn("shot(s) 1 list nobody", seen_ask[0]); self.assertIn("unless the request itself asks for scenery", seen_ask[0])

    def test_nothing_is_asked_when_every_shot_has_the_subject_or_there_is_no_cast(self):
        seen_ask.clear(); run_direct([CAR], self.CAR_CHARS, [["car"], ["car"]]); self.assertEqual(seen_ask, [])
        seen_ask.clear(); run_direct([NOBODY], [], [[], []]); self.assertEqual(seen_ask, [])                          # no subject in the request: empty shots are fine

    def test_the_analyze_prompt_names_every_kind_of_subject_and_the_rule(self):
        seen = []; run_direct([CAR], self.CAR_CHARS, [["car"], ["car"]], seen)
        u = next(u for s_, u in seen if "before anything is drawn. First" in s_); self.assertIn("vehicle or product", u); self.assertIn("EVERY shot shows the lead", u)


class IdReadingTests(unittest.TestCase):
    S = [[{}, {}], [{}], [{}, {}]]

    def test_ids_are_read_whatever_shape_the_model_wrote_them_in(self):
        ids = director.subject_ids
        self.assertEqual(ids(["1.1", "3.2"], self.S), (["1.1", "3.2"], [])); self.assertEqual(ids([1.1, 3.1], self.S), (["1.1", "3.1"], []))              # floats
        self.assertEqual(ids(["1-2", " 3.1 "], self.S), (["1.2", "3.1"], []))
        self.assertEqual(ids([2], self.S), (["2.1"], [])); self.assertEqual(ids([2.0], self.S), (["2.1"], []))                                           # a bare number is the photo's one subject
        self.assertEqual(ids([1, 3], self.S), ([], ["1", "3"]))                                                                                         # a photo with two people is not guessed
        self.assertEqual(ids(["9.9", "x", None], self.S)[0], []); self.assertEqual(ids(None, self.S), ([], []))

    def test_a_wrong_id_is_named_in_the_ask_and_the_corrected_answer_links_the_photo(self):
        asked = []
        def fake(c, system, user, temperature=0.6, max_tokens=4000, check=None, attempts=3):
            if "before anything is drawn. First" in system:
                first = {"kind": "story", "intent": "i", "audience": "a", "characters": [{"id": "a", "name": "Ann", "in": [1, 2]}], "rules": ["r"], "open_details": ["d"], "title": "T", "shot_list": [{"topic": "t", "purpose": "p", "characters": ["a"]}]}
                msg = check(first); asked.append(msg); self.assertGreater(attempts, 3)
                fixed = dict(first, characters=[{"id": "a", "name": "Ann", "in": ["1.1"]}, {"id": "b", "name": "Bo", "in": ["1.2"]}]); self.assertIsNone(check(fixed)); return fixed
            return make_llm([], [[]])(c, system, user, temperature, max_tokens, check)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(llm, "ask_json", fake), mock.patch.object(llm, "ask_about_image", return_value=COUPLE):
            (Path(d) / "jobs").mkdir(); job = Job.create(Path(d) / "jobs", {"query": "q", "count": 1, "aspect": "16:9", "video": True}); job.add_references([photo(d)]); logs = []; job.log = logs.append
            job.write("plan.json", {"count": 1, "needs_web": False, "research_questions": [], "tone": "t", "narrated": True}); job.write("research.json", [])
            an = director.analyze(job, CFG, CAPS, job.read("plan.json"), job.state["request"], [], 1, "")
        self.assertIn("you wrote 1, 2", asked[0]); self.assertEqual([(c["id"], c["origin"], c["in"]) for c in an["characters"]], [("a", "photo", ["1.1"]), ("b", "photo", ["1.2"])]); self.assertFalse(any("NOT USED" in l for l in logs))

    def test_the_brief_says_that_different_clothes_are_not_new_people(self):
        text = director.photo_brief({"references": ["a", "b"]}, [json_subs(COUPLE), json_subs(COUPLE)]); self.assertIn("do NOT make a new character because the clothes differ", text)


class NormCastTests(unittest.TestCase):
    S = [json_subs(COUPLE), json_subs(SOLO), json_subs(NOBODY)]

    def norm(self, chars, shots=None):
        return director._norm_cast({"characters": chars, "shot_list": shots or [{"characters": [c["id"] for c in chars if isinstance(c, dict)]}]}, len(shots or [1]), self.S)

    def test_a_character_is_from_the_photos_only_when_it_names_subjects_and_an_id_has_one_owner(self):
        an = self.norm([{"id": "a", "name": "Ann", "in": ["1.2", "9.9"]}, {"id": "b", "name": "Bo", "in": ["1.1", "2.1", "1.2"]}, {"id": "c", "name": "Cy", "origin": "photo"}, {"id": "d", "name": "Di", "in": "1.1"}])
        got = {c["id"]: (c["origin"], c["in"], c["photos"]) for c in an["characters"]}
        self.assertEqual(got["a"], ("photo", ["1.2"], [1])); self.assertEqual(got["b"], ("photo", ["1.1", "2.1"], [1, 2]))          # 9.9 does not exist; 1.2 is Ann's
        self.assertEqual(got["c"][0], "invented"); self.assertEqual(got["d"][0], "invented")                                    # "photo" without ids is not a photo person; ids in the wrong shape are ignored

    def test_pointers_say_where_a_person_is_only_when_the_photo_shows_several(self):
        an = self.norm([{"id": "a", "name": "Ann", "in": ["1.2", "2.1"]}, {"id": "b", "name": "Bo", "in": ["1.1"]}])
        self.assertEqual({c["id"]: c["pointers"] for c in an["characters"]}, {"a": {1: "right", 2: ""}, "b": {1: "left"}})
        two_left = [[{"at": "left", "look": "tall man in a blue coat"}, {"at": "left", "look": "child in yellow"}]]
        an = director._norm_cast({"characters": [{"id": "a", "name": "A", "in": ["1.1"]}], "shot_list": []}, 1, two_left); self.assertEqual(an["characters"][0]["pointers"], {1: "tall man in a"})   # two share a place: a few words of the look

    def test_nobody_is_made_up(self):
        an = self.norm([])                                                                                                 # photos show people but the model named no one: no photo character appears
        self.assertEqual(an["characters"], []); self.assertEqual(an["shot_list"][0]["characters"], [])
        an = director._norm_cast({"characters": [{"id": "a", "name": "A", "origin": "photo", "in": ["1.1"]}], "shot_list": []}, 1, [json_subs(NOBODY)])           # the only photo shows no one
        self.assertEqual(an["characters"][0]["origin"], "invented"); self.assertEqual(an["characters"][0]["photos"], [])
        an = director._norm_cast({"characters": [{"id": "a", "name": "A", "in": ["1.1"]}], "shot_list": []}, 1)                                                      # no photos at all
        self.assertEqual(an["characters"][0]["origin"], "invented")

    def test_photo_people_get_distinct_names(self):
        an = self.norm([{"id": "a", "name": "Sam", "in": ["1.1"]}, {"id": "b", "name": "sam", "in": ["1.2"]}]); self.assertEqual(len({c["name"].lower() for c in an["characters"]}), 2)


def person(i, name, photos, pointers=None): return {"id": i, "name": name, "photo": True, "photos": photos, "pointers": pointers or {}}


class SelectRefsTests(unittest.TestCase):
    def test_a_group_photo_that_shows_everyone_is_used_alone_for_any_number_of_people(self):
        for n in (1, 2, 3, 4):
            cast = [person(f"p{i}", f"P{i}", [1], {1: f"spot{i}"}) for i in range(1, n + 1)]
            order, labels = director.select_refs(cast, [c["id"] for c in cast], 1); self.assertEqual(order, [1]); self.assertEqual(len(labels), n)
        self.assertEqual(labels["p3"], "P3 (spot3 in reference image 1)")

    def test_only_the_people_in_the_picture_count_and_photos_rotate(self):
        cast = [person("a", "Ann", [1, 3, 2], {1: "left", 3: "left", 2: "left"}), person("b", "Bo", [1, 3, 2], {1: "right", 3: "right", 2: "right"})]
        self.assertEqual([director.select_refs(cast, ["a", "b"], k)[0] for k in (1, 2, 3, 4)], [[1], [2], [3], [1]])             # one reference per picture, every photo gets its turn
        order, labels = director.select_refs(cast, ["b"], 1); self.assertEqual((order, labels), ([1], {"b": "Bo (right in reference image 1)"}))     # Bo alone: still the group photo, with the pointer to Bo
        self.assertEqual(director.select_refs(cast, [], 1), ([], {}))

    def test_a_group_photo_plus_a_solo_photo_and_the_cap(self):
        cast = [person("a", "Ann", [1], {1: "left"}), person("b", "Bo", [1], {1: "right"}), person("c", "Cy", [2]), person("d", "Di", [3])]
        order, labels = director.select_refs(cast, ["a", "b", "c"], 1); self.assertEqual(order, [1, 2]); self.assertEqual(labels["c"], "Cy (reference image 2)")      # the group photo covers two, Cy's own photo the third
        order, labels = director.select_refs(cast, ["a", "b", "c", "d"], 1); self.assertEqual(order, [1, 2]); self.assertNotIn("d", labels)                              # cap 2: Di is described by words only
        self.assertEqual(director.select_refs(cast, ["a", "b", "c", "d"], 1, max_refs=3)[0], [1, 2, 3])
        self.assertEqual(director.select_refs(cast, ["c"], 1)[0], [2]); self.assertEqual(director.select_refs([{"id": "x", "name": "X"}], ["x"], 1), ([], {}))            # people without photos need none


class DirectorFlowTests(unittest.TestCase):
    def check_prompts(self, dr, it):
        for x in it["items"]:
            total = len(x["image_prompt"].rstrip(". ")) + 2 + len(dr["style_line"]) + 2 + len(CFG["policy"].get("image_text", ""))
            self.assertLessEqual(total, CFG["limits"]["image_prompt_chars"], x["image_prompt"])

    def test_a_couple_in_three_photos_gets_one_photo_per_picture_and_only_the_people_present(self):
        chars = [{"id": "a", "name": "Ann", "role": "r", "in": ["1.1", "2.1", "3.1"]}, {"id": "b", "name": "Bo", "role": "r", "in": ["1.2", "2.2", "3.2"]}]
        dr, it, _ = run_direct([COUPLE] * 3, chars, [["a", "b"], ["b"], ["a", "b"], []])
        self.assertEqual([x.get("refs") for x in it["items"]], [[1], [2], [3], None])                                             # one reference each, rotating; none when no one is in the picture
        p1, p2, p4 = (x["image_prompt"] for x in (it["items"][0], it["items"][1], it["items"][3]))
        self.assertTrue(p1.startswith("Ann (left in reference image 1): outfit of a. Bo (right in reference image 1): outfit of b. Only the people come from the references."))
        self.assertTrue(p2.startswith("Bo (right in reference image 1): outfit of b. Only the people") and "Ann" not in p2)       # Bo alone: photo 2 is the only reference of THIS picture (numbered per picture); Ann is not named
        self.assertNotIn("reference image", p4); self.check_prompts(dr, it)

    def test_three_people_one_group_photo_and_one_solo_photo(self):
        chars = [{"id": "a", "name": "Ann", "in": ["1.1"]}, {"id": "b", "name": "Bo", "in": ["1.2"]}, {"id": "c", "name": "Cy", "in": ["2.1"]}]
        dr, it, _ = run_direct([COUPLE, SOLO], chars, [["a", "b", "c"], ["c"], ["a"]])
        self.assertEqual([x.get("refs") for x in it["items"]], [[1, 2], [2], [1]])
        self.assertIn("Cy (reference image 2)", it["items"][0]["image_prompt"]); self.assertIn("Ann (left in reference image 1)", it["items"][2]["image_prompt"]); self.check_prompts(dr, it)

    def test_one_person_one_photo(self):
        dr, it, _ = run_direct([SOLO], [{"id": "me", "name": "the person", "in": ["1.1"]}], [["me"], ["me"]])
        self.assertEqual([x.get("refs") for x in it["items"]], [[1], [1]]); self.assertTrue(it["items"][0]["image_prompt"].startswith("Person (reference image 1): outfit of me. Only the people"))

    def test_photos_without_people_do_not_make_anyone_up(self):
        seen = []; dr, it, logs = run_direct([NOBODY, NOBODY], [], [[], []], seen)
        self.assertEqual(dr["cast"], []); self.assertTrue(all("refs" not in x for x in it["items"])); self.assertTrue(all("reference image" not in x["image_prompt"] for x in it["items"]))
        self.assertTrue(any("no one" in l for l in logs)); analyze = next(u for s_, u in seen if "before anything is drawn. First" in s_); self.assertIn("Photo 1: no one", analyze)

    def test_when_the_model_ignores_the_photos_it_is_asked_three_times_then_the_answer_stands_and_the_log_says_so(self):
        asked = []
        def fake(c, system, user, temperature=0.6, max_tokens=4000, check=None, attempts=3):
            if "before anything is drawn. First" in system:
                o = {"kind": "story", "intent": "i", "audience": "a", "characters": [], "rules": ["r"], "open_details": ["d"], "title": "T", "shot_list": [{"topic": "t", "purpose": "p", "characters": []}]}
                for _ in range(5):
                    msg = check(o)
                    if msg is None: break
                    asked.append(msg)
                return o
            return make_llm([], [[]])(c, system, user, temperature, max_tokens, check)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(llm, "ask_json", fake), mock.patch.object(llm, "ask_about_image", return_value=COUPLE):
            (Path(d) / "jobs").mkdir(); job = Job.create(Path(d) / "jobs", {"query": "q", "count": 1, "aspect": "16:9", "video": True}); job.add_references([photo(d)])
            job.write("plan.json", {"count": 1, "needs_web": False, "research_questions": [], "tone": "t", "narrated": True}); job.write("research.json", [])
            logs = []; job.log = logs.append; director.direct(job, CFG, CAPS); self.assertEqual(len(asked), 3); self.assertIn("1.1", asked[0]); self.assertEqual(job.read("direction.json")["cast"], [])           # no one is forced in
            self.assertTrue(any("photos NOT USED" in l for l in logs))                                                                        # and the failure is visible

    def test_a_photo_person_is_asked_for_an_outfit_only_and_the_outfit_is_accepted_as_the_text(self):
        seen = []
        def fake(c, system, user, temperature=0.6, max_tokens=4000, check=None, attempts=3):
            seen.append(user); o = make_llm([{"id": "a", "name": "Ann", "in": ["1.1"]}, {"id": "n", "name": "Nik", "origin": "invented"}], [["a", "n"]])(c, system, user, temperature, max_tokens, None)
            if "fixing every open detail" in system: o = dict(o, cast=[{"id": "a", "outfit": "navy coat, red scarf"}, {"id": "n", "appearance": "tall, grey beard, green apron"}])
            if check: assert check(o) is None, check(o)
            return o
        with tempfile.TemporaryDirectory() as d, mock.patch.object(llm, "ask_json", fake), mock.patch.object(llm, "ask_about_image", return_value=SOLO):
            (Path(d) / "jobs").mkdir(); job = Job.create(Path(d) / "jobs", {"query": "q", "count": 1, "aspect": "16:9", "video": True}); job.add_references([photo(d)])
            job.write("plan.json", {"count": 1, "needs_web": False, "research_questions": [], "tone": "t", "narrated": True}); job.write("research.json", []); director.direct(job, CFG, CAPS)
            cast = job.read("direction.json")["cast"]
        self.assertEqual([c["appearance"] for c in cast], ["navy coat, red scarf", "tall, grey beard, green apron"])              # a made-up character still gets a full appearance
        self.assertTrue(any('{"id", "outfit"}' in u and "never face, hair, age or build" in u for u in seen))                 # and the person from the photos is told to give clothes only

    def test_without_photos_nothing_changes(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(llm, "ask_json", make_llm([{"id": "h", "name": "Harry", "origin": "named", "role": "r"}], [["h"]])), mock.patch.object(llm, "ask_about_image") as look:
            (Path(d) / "jobs").mkdir(); job = Job.create(Path(d) / "jobs", {"query": "q", "count": 1, "aspect": "16:9", "video": True})
            job.write("plan.json", {"count": 1, "needs_web": False, "research_questions": [], "tone": "t", "narrated": True}); job.write("research.json", []); director.direct(job, CFG, CAPS)
            it = job.read("items.json"); self.assertEqual(look.call_count, 0); self.assertTrue(all("refs" not in x for x in it["items"])); self.assertNotIn("reference image", it["items"][0]["image_prompt"])


if __name__ == "__main__":
    unittest.main()
