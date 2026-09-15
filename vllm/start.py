"""Discover complete Safetensors checkpoints in an HF cache and launch vLLM."""
import argparse
import json
import os
from pathlib import Path
import sys


def readable(path):
    try:
        with path.open('rb') as handle:
            return bool(handle.read(1))
    except OSError:
        return False


def checkpoint(path):
    config = json.loads((path / 'config.json').read_text())
    if not config.get('architectures') or (path / 'adapter_config.json').exists():
        return False
    index = path / 'model.safetensors.index.json'
    if index.exists():
        weights = set(json.loads(index.read_text()).get('weight_map', {}).values())
        # Index entries are filenames relative to this snapshot.
        if any(Path(w).is_absolute() or '..' in Path(w).parts for w in weights):
            return False
        files = [path / w for w in weights]
    else:
        files = [path / 'model.safetensors']
    return bool(files) and all(readable(p) for p in files) and any(
        readable(path / name) for name in ('tokenizer.json', 'tokenizer.model', 'spiece.model'))


def discover(root):
    if (root / 'hub').is_dir():
        root = root / 'hub'
    results = {}
    for repo in sorted(root.glob('models--*')):
        repo_id = repo.name.removeprefix('models--').replace('--', '/')
        for snapshot in sorted((repo / 'snapshots').glob('*')):
            try:
                if checkpoint(snapshot):
                    results[f'{repo_id}@{snapshot.name}'] = snapshot
            except (OSError, ValueError, TypeError) as exc:
                print(f'discovery: skipping {repo_id}@{snapshot.name}: {exc}', file=sys.stderr)
    return results


def select(models, requested=''):
    if requested in models:
        return requested, models[requested]
    repos = {key.split('@')[0] for key in models}
    if not requested and len(repos) == 1:
        requested = next(iter(repos))
    candidates = {k: p for k, p in models.items() if k.split('@')[0] == requested}
    if not candidates:
        raise ValueError('Set VLLM_MODEL to a listed repo ID or repo@revision; '
                         'auto-selection requires exactly one cached model repository.')
    # Prefer the cached main ref. Never guess among multiple non-main revisions.
    for key, path in candidates.items():
        ref = path.parent.parent / 'refs' / 'main'
        if ref.is_file() and ref.read_text().strip() == path.name:
            return key, path
    if len(candidates) == 1:
        return next(iter(candidates.items()))
    raise ValueError('Multiple cached revisions without a complete main; set VLLM_MODEL=repo@revision.')


def command(model_id, path, env):
    extra = json.loads(env.get('VLLM_EXTRA_ARGS', '[]'))
    if not isinstance(extra, list) or not all(isinstance(arg, str) for arg in extra):
        raise ValueError('VLLM_EXTRA_ARGS must be a JSON array of strings')
    reserved = {'--model', '--served-model-name', '--host', '--port', '--api-key', '--config'}
    if any(arg.split('=')[0] in reserved for arg in extra):
        raise ValueError('VLLM_EXTRA_ARGS must not override model, network, API key, or config settings')
    if not env.get('VLLM_API_KEY'):
        raise ValueError('VLLM_API_KEY is required')
    return ['vllm', 'serve', str(path), '--served-model-name', model_id.split('@')[0],
            '--host', '0.0.0.0', '--port', '8000',
            '--max-model-len', env.get('VLLM_MAX_MODEL_LEN', '8192'),
            '--gpu-memory-utilization', env.get('VLLM_GPU_MEMORY_UTILIZATION', '0.50'),
            '--max-num-seqs', env.get('VLLM_MAX_NUM_SEQS', '4'),
            '--safetensors-load-strategy', 'lazy', *extra]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, default=Path('/hf-cache'))
    parser.add_argument('--list', action='store_true', help='list candidates without loading weights')
    args = parser.parse_args()
    try:
        if not args.cache_dir.is_dir():
            raise ValueError(f'cache directory does not exist: {args.cache_dir}')
        models = discover(args.cache_dir)
        for model in models:
            print(f'discovery: {model}', flush=True)
        print(f'discovery: {len(models)} complete checkpoint candidate(s); '
              'vLLM validates architecture/quantization at load time', flush=True)
        if args.list:
            return
        key, path = select(models, os.environ.get('VLLM_MODEL', ''))
        argv = command(key, path, os.environ)
        print(f'Starting vLLM: {key}; API model ID: {key.split("@")[0]}', flush=True)
        # vLLM reads VLLM_API_KEY itself; keep it out of command-line logs.
        os.execvp(argv[0], argv)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f'vllm startup: {exc}\n')


if __name__ == '__main__':
    main()
