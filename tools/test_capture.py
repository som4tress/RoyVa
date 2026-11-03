import unittest
from pathlib import Path
from unittest.mock import patch
import capture

class CaptureTests(unittest.TestCase):
    def test_excludes_private_state_and_keeps_runtime_configuration(self):
        for name in ['api.env','service.json','tunnel.json','auth.json','state.json']:
            self.assertFalse(capture.eligible('opencode',Path(name)))
        for name in capture.OPENCODE_JSON:
            self.assertTrue(capture.eligible('opencode',Path(name)))

    def test_sources_and_generated_outputs_are_distinct(self):
        self.assertTrue(capture.eligible('opencode',Path('lib/router.mjs')))
        self.assertFalse(capture.eligible('llm-server',Path('benchmark-results.json')))
        self.assertTrue({'node_modules','dist','build','bundle','.git'}.issubset(capture.SKIP))

    def test_known_credentials_are_redacted_without_touching_the_source(self):
        original=b'const credential="diagnostic-secret-value";'
        with patch.object(capture,'known_secrets',return_value=['diagnostic-secret-value']):
            result,redacted=capture.sanitize(original)
        self.assertTrue(redacted)
        self.assertNotIn(b'diagnostic-secret-value',result)
        self.assertIn(b'diagnostic-secret-value',original)

if __name__=='__main__':unittest.main()
