import tempfile
import unittest
from unittest import mock

from img_video import config, pipeline, research
from img_video.jobs import Job

CFG, CAPS = config.load()


class SuppliedResearchTests(unittest.TestCase):
    def test_supplied_text_skips_the_gateway(self):
        with tempfile.TemporaryDirectory() as d:
            job = Job.create(d, {"query": "q", "count": 2, "aspect": "1:1", "research_text": "headline one. headline two."})
            job.write("plan.json", {"count": 2, "needs_web": True, "research_questions": ["what is new?"], "tone": "x"})
            with mock.patch.object(research, "ask", side_effect=AssertionError("the gateway must not be called")):
                pipeline.do_research(job, CFG, CAPS)
            out = job.read("research.json")
            self.assertEqual(out[0]["text"], "headline one. headline two."); self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
