import copy
import unittest

from img_video import config, pipeline

CFG, CAPS = config.load()


def cfg_with(scale):
    c = copy.deepcopy(CFG); c.setdefault("pipeline", {})["video_picture_scale"] = scale
    return c


class PictureSizeTests(unittest.TestCase):
    def test_scale_zero_means_everything_uses_the_full_aspect_size(self):
        c = cfg_with(0)
        for a, full in CAPS["aspect"].items():
            self.assertEqual(pipeline.picture_size(c, CAPS, {"aspect": a, "video": True}), tuple(full))
            self.assertEqual(pipeline.picture_size(c, CAPS, {"aspect": a}), tuple(full))

    def test_the_shipped_config_never_shrinks_pictures_or_sets(self):
        for a, full in CAPS["aspect"].items():
            self.assertEqual(pipeline.picture_size(CFG, CAPS, {"aspect": a}), tuple(full))

    def test_scale_applies_to_video_only_never_to_pictures_or_sets(self):
        c = cfg_with(1.5)
        for a, full in CAPS["aspect"].items():
            self.assertEqual(pipeline.picture_size(c, CAPS, {"aspect": a}), tuple(full))                 # a set / single image
            self.assertEqual(pipeline.picture_size(c, CAPS, {"aspect": a, "video": False}), tuple(full))
            w, h = pipeline.picture_size(c, CAPS, {"aspect": a, "video": True})
            self.assertTrue(w % 16 == 0 and h % 16 == 0 and w <= full[0] and h <= full[1])

    def test_scaled_video_sizes_for_each_aspect(self):
        c = cfg_with(1.5)
        self.assertEqual(pipeline.picture_size(c, CAPS, {"aspect": "1:1", "video": True}), (640, 640))
        self.assertEqual(pipeline.picture_size(c, CAPS, {"aspect": "9:16", "video": True}), (480, 864))
        self.assertEqual(pipeline.picture_size(c, CAPS, {"aspect": "16:9", "video": True}), (864, 480))

    def test_a_huge_scale_is_capped_at_the_full_size(self):
        self.assertEqual(pipeline.picture_size(cfg_with(10), CAPS, {"aspect": "1:1", "video": True}), (1024, 1024))

    def test_the_images_stage_fingerprint_is_unchanged_for_sets_and_differs_for_video_sizes(self):
        items = {"items": []}; base = {"llm": "x"}
        a = pipeline._images_inputs(base, CFG, {"aspect": "1:1"}, items, "s", CAPS)
        self.assertNotIn("video_size", a)
        v0 = pipeline._images_inputs(base, cfg_with(0), {"aspect": "1:1", "video": True}, items, "s", CAPS)
        v1 = pipeline._images_inputs(base, cfg_with(1.5), {"aspect": "1:1", "video": True}, items, "s", CAPS)
        self.assertNotEqual(pipeline.fingerprint(v0), pipeline.fingerprint(v1))


if __name__ == "__main__":
    unittest.main()
