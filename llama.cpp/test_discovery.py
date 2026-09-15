import importlib.util
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location("discovery", Path(__file__).with_name("discover-models.py"))
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.models = self.root / "models"
        self.models.mkdir()
        self.output = self.root / "output"

    def gguf(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF" + b"\x00" * 20)
        return path

    def run_discovery(self, roots=None):
        return discovery.discover(roots or [("models", self.models)], self.output)

    def test_empty_sources(self):
        self.assertEqual(self.run_discovery(), [])
        self.assertEqual((self.output / "models.ini").read_text(), "version = 1\n")

    def test_multiple_quants_and_safe_paths(self):
        self.gguf(self.models / "odd [folder]; name" / "q4.gguf")
        self.gguf(self.models / "odd [folder]; name" / "q8.gguf")
        (self.models / "weights.safetensors").write_text("ignored")
        ids = self.run_discovery()
        self.assertEqual(len(ids), 2)
        self.assertIn("%5Bfolder%5D", ids[0])
        links = list(self.output.glob("*/model.gguf"))
        self.assertEqual(len(links), 2)
        self.assertTrue(all(link.is_symlink() and link.read_bytes().startswith(b"GGUF") for link in links))

    def test_hf_symlinks_and_duplicate_snapshots(self):
        cache = self.root / "hub"
        blob = self.gguf(cache / "models--org--repo" / "blobs" / "hash")
        for revision in ("aaa", "bbb"):
            snapshot = cache / "models--org--repo" / "snapshots" / revision
            snapshot.mkdir(parents=True)
            (snapshot / "q4.gguf").symlink_to("../../blobs/hash")
        self.gguf(self.models / "other.gguf")
        ids = self.run_discovery([("models", self.models), ("hf", cache)])
        self.assertEqual(len(ids), 2)
        self.assertTrue(ids[1].startswith("hf/models--org--repo/snapshots/aaa/"))
        self.assertEqual(blob.read_bytes()[:4], b"GGUF")

    def test_shards_and_projector(self):
        for i in (1, 2):
            self.gguf(self.models / f"vision-0000{i}-of-00002.gguf")
        self.gguf(self.models / "mmproj-F16.gguf")
        self.assertEqual(len(self.run_discovery()), 1)
        self.assertEqual(len(list(self.output.glob("*/model-*.gguf"))), 2)
        self.assertIn("mmproj = ", (self.output / "models.ini").read_text())
        self.assertEqual(len(self.run_discovery()), 1)  # restart regenerates safely

    def test_incomplete_invalid_and_broken_files(self):
        self.gguf(self.models / "incomplete-00001-of-00002.gguf")
        (self.models / "broken.gguf").symlink_to("missing")
        (self.models / "invalid.gguf").write_bytes(b"not a model")
        self.assertEqual(self.run_discovery(), [])

    def test_ambiguous_projectors(self):
        self.gguf(self.models / "model.gguf")
        self.gguf(self.models / "mmproj-a.gguf")
        self.gguf(self.models / "mmproj-b.gguf")
        self.assertEqual(len(self.run_discovery()), 1)
        self.assertNotIn("mmproj = ", (self.output / "models.ini").read_text())


if __name__ == "__main__":
    unittest.main()
