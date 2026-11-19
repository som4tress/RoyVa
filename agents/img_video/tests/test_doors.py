import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("check_3090_doors", ROOT / "tools" / "check_3090_doors.py")
doors = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(doors)


class DoorTests(unittest.TestCase):
    def tree(self, files):
        d = Path(tempfile.mkdtemp())
        for rel, text in files.items():
            p = d / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
        return d

    def test_the_repo_has_only_the_reviewed_doors(self):
        self.assertEqual(doors.scan(str(ROOT)), [])

    def test_every_kind_of_new_door_is_caught(self):
        d = self.tree({"mcp/new/client.py": "import urllib.request\nurllib.request.urlopen(base + '/prompt')\n", "agent2/cfg.toml": 'url = "http://somdutta-linux.local:8188"\n', "bridge/new.mjs": "exec('ssh box ls')\n",
                       "a/b.py": "post(base + \"/free\")\n", "x/y.sh": "scp file 192.168.4.55:\n"})
        found = " | ".join(doors.scan(str(d)))
        for expected in ("mcp/new/client.py:2", "agent2/cfg.toml:1", "bridge/new.mjs:1", "a/b.py:1", "x/y.sh:1"): self.assertIn(expected, found)

    def test_reviewed_files_tests_docs_runtime_and_manual_scripts_are_not_flagged(self):
        d = self.tree({"agents/img_video/img_video/comfy.py": "post('/prompt')\n", "bridge/whisper.mjs": "ssh host\n", "tests/test_x.py": "'/prompt' 8188 ssh\n", "bridge/x.test.mjs": "ssh\n", "docs/n.md": "8188\n",
                       "runtime/data/a.py": "8188\n", "scripts/remote/run.sh": "ssh somdutta-linux.local\n", "node_modules/p/i.js": "ssh\n"})
        self.assertEqual(doors.scan(str(d)), [])

    def test_the_forbidden_free_call_is_never_allowed_anywhere(self):
        self.assertEqual(doors.DOORS[r"""['"]/free['"]"""]["allowed"], {})


if __name__ == "__main__":
    unittest.main()
