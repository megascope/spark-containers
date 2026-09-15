import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('litellm_start', Path(__file__).with_name('start.py'))
start = importlib.util.module_from_spec(spec)
spec.loader.exec_module(start)


class OptionalRoutesTests(unittest.TestCase):
    def test_all_optional_upstream_combinations(self):
        config = {'model_list': [
            {'model_name': name, 'litellm_params': {'api_base': 'os.environ/' + name}}
            for name in ('LLAMA_API_BASE', 'OLLAMA_API_BASE', 'VLLM_API_BASE')]}
        for ollama in ('', 'http://ollama'):
            for vllm in ('', 'http://vllm'):
                env = {'OLLAMA_API_BASE': ollama, 'VLLM_API_BASE': vllm}
                names = [r['model_name'] for r in start.enabled_routes(copy.deepcopy(config), env)['model_list']]
                self.assertIn('LLAMA_API_BASE', names)
                self.assertEqual('OLLAMA_API_BASE' in names, bool(ollama))
                self.assertEqual('VLLM_API_BASE' in names, bool(vllm))


if __name__ == '__main__':
    unittest.main()
