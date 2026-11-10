import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import preregister


class FreezeSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        for directory in ("src", "tests", "data", "docs", "runs"):
            (self.root / directory).mkdir()
        for name in ("src/system.py", "tests/test_system.py", "data/cases.jsonl", "data/emails.jsonl",
                     "docs/GATE.json", "docs/PREREG.md", "docs/MODELS.json", "docs/SELECTION.json",
                     "docs/RUNTIME_ATTESTATION.json", "requirements.txt"):
            (self.root / name).write_text("frozen\n")
        p1 = patch.object(preregister, "ROOT_PATH", self.root)
        p2 = patch.object(preregister, "MANIFEST", self.root / "docs/PREREG.manifest.json")
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def test_each_frozen_input_change_is_refused(self):
        preregister.freeze()
        for name in preregister.frozen_paths():
            p = self.root / name
            original = p.read_bytes()
            p.write_text("changed")
            with self.subTest(path=name), self.assertRaises(ValueError):
                preregister.verify()
            p.write_bytes(original)
        preregister.verify()

    def test_added_source_file_cannot_escape_freeze(self):
        preregister.freeze()
        (self.root / "src/late.py").write_text("changed")
        with self.assertRaises(ValueError):
            preregister.verify()

    def test_freeze_after_heldout_output_is_refused(self):
        (self.root / "runs/candidate_h1.shard0.jsonl").write_text('{}\n')
        with self.assertRaises(ValueError):
            preregister.freeze()


if __name__ == "__main__":
    unittest.main()
