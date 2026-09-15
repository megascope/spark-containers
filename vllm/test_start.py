import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('vllm_start', Path(__file__).with_name('start.py'))
start = importlib.util.module_from_spec(spec)
spec.loader.exec_module(start)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def snapshot(self, repo='org/model', revision='rev1'):
        repo_path = self.root / ('models--' + repo.replace('/', '--'))
        path = repo_path / 'snapshots' / revision
        path.mkdir(parents=True)
        (path / 'config.json').write_text(json.dumps({'architectures': ['Qwen3ForCausalLM']}))
        (path / 'tokenizer.json').write_text('{}')
        blob = repo_path / 'blobs' / revision
        blob.parent.mkdir(exist_ok=True)
        blob.write_bytes(b'weights')
        (path / 'model.safetensors').symlink_to('../../blobs/' + revision)
        return path

    def test_auto_single_and_explicit(self):
        path = self.snapshot()
        models = start.discover(self.root)
        self.assertEqual(start.select(models), ('org/model@rev1', path))
        self.assertEqual(start.select(models, 'org/model')[1], path)
        self.assertEqual(start.select(models, 'org/model@rev1')[1], path)

    def test_multiple_models_require_selection(self):
        self.snapshot()
        self.snapshot('org/second')
        models = start.discover(self.root)
        with self.assertRaisesRegex(ValueError, 'VLLM_MODEL'):
            start.select(models)
        self.assertEqual(start.select(models, 'org/second')[0], 'org/second@rev1')

    def test_main_revision_and_ambiguity(self):
        self.snapshot()
        current = self.snapshot(revision='rev2')
        models = start.discover(self.root)
        with self.assertRaisesRegex(ValueError, 'Multiple cached revisions'):
            start.select(models)
        ref = current.parent.parent / 'refs' / 'main'
        ref.parent.mkdir()
        ref.write_text('rev2')
        self.assertEqual(start.select(models)[1], current)

    def test_missing_shard_tokenizer_and_gguf(self):
        path = self.snapshot()
        (path / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': {'a': 'missing.safetensors'}}))
        self.assertEqual(start.discover(self.root), {})
        (path / 'model.safetensors.index.json').unlink()
        (path / 'tokenizer.json').unlink()
        self.assertEqual(start.discover(self.root), {})
        (path / 'tokenizer.json').write_text('{}')
        (path / 'model.safetensors').unlink()
        (path / 'model.gguf').write_bytes(b'GGUF')
        self.assertEqual(start.discover(self.root), {})

    def test_complete_shards_and_parent_cache(self):
        path = self.snapshot()
        (path / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': {'a': 'model.safetensors'}}))
        self.assertEqual(len(start.discover(self.root)), 1)
        hub = self.root / 'hub'
        hub.mkdir()
        (self.root / 'models--org--model').rename(hub / 'models--org--model')
        self.assertEqual(len(start.discover(self.root)), 1)

    def test_args_and_no_secret_in_argv(self):
        env = {'VLLM_API_KEY': 'private-test-value', 'VLLM_EXTRA_ARGS': '["--enforce-eager"]'}
        argv = start.command('org/model@rev', Path('/cache/snapshot'), env)
        self.assertNotIn('private-test-value', argv)
        self.assertIn('--enforce-eager', argv)
        self.assertEqual(argv[argv.index('--served-model-name') + 1], 'org/model')
        for extra in ('{}', '[1]', '["--host=0.0.0.0"]'):
            with self.assertRaises(ValueError):
                start.command('org/model', Path('/cache'), dict(env, VLLM_EXTRA_ARGS=extra))


if __name__ == '__main__':
    unittest.main()
