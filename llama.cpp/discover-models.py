#!/usr/bin/env python3
"""Register local GGUFs for llama.cpp without copying model data."""

import argparse
import hashlib
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote


SHARD = re.compile(r"^(.*)-(\d{5})-of-(\d{5})\.gguf$", re.IGNORECASE)


def warn(message):
    print(f"discovery: {message}", file=sys.stderr)


def readable_gguf(path):
    try:
        with path.open("rb") as handle:
            if handle.read(4) != b"GGUF":
                raise ValueError("missing GGUF header")
        return True
    except (OSError, ValueError) as exc:
        warn(f"skipping {path}: {exc}")
        return False


def discover(roots, output):
    """Write a preset and symlinks under output; return the discovered IDs."""
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    entries = ["version = 1\n"]
    ids = []
    seen = set()
    for prefix, root in roots:
        if root is None:
            continue
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"not a directory: {root}")
        # Do not follow directory symlinks: avoid loops and unrelated trees.
        # HF snapshot file symlinks are followed when opening each GGUF.
        for directory, dirs, files in os.walk(root, onerror=lambda exc: warn(str(exc))):
            dirs.sort()
            folder = Path(directory)
            ggufs = sorted(name for name in files if name.lower().endswith(".gguf"))
            projectors = [name for name in ggufs if name.lower().startswith("mmproj")]
            for name in ggufs:
                if name in projectors or name.lower().startswith(("mtp-", "draft-")):
                    continue
                path = folder / name
                match = SHARD.fullmatch(name)
                if match and int(match[2]) != 1:
                    continue
                shards = [path]
                if match:
                    count = int(match[3])
                    if count < 1:
                        warn(f"skipping invalid shard count: {path}")
                        continue
                    shards = [folder / f"{match[1]}-{i:05d}-of-{count:05d}.gguf"
                              for i in range(1, count + 1)]
                if not all(readable_gguf(part) for part in shards):
                    continue
                projector = None
                if len(projectors) == 1 and readable_gguf(folder / projectors[0]):
                    projector = folder / projectors[0]
                elif len(projectors) > 1:
                    warn(f"multiple projectors beside {path}; serving without vision")
                # Resolve HF symlinks to deduplicate snapshots and overlapping roots.
                identity = (tuple(part.resolve() for part in shards),
                            projector.resolve() if projector else None)
                if identity in seen:
                    continue
                seen.add(identity)
                relative = path.relative_to(root).with_suffix("").as_posix()
                model_id = prefix + "/" + quote(relative, safe="/-_.")
                # Fixed filenames keep arbitrary source paths out of the INI syntax.
                staged = output / hashlib.sha256(model_id.encode()).hexdigest()
                staged.mkdir(exist_ok=True)
                targets = []
                for i, part in enumerate(shards, 1):
                    filename = (f"model-{i:05d}-of-{len(shards):05d}.gguf"
                                if match else "model.gguf")
                    link = staged / filename
                    link.unlink(missing_ok=True)
                    link.symlink_to(part)
                    targets.append(link)
                entries.append(f"[{model_id}]\nmodel = {targets[0]}\n")
                if projector:
                    link = staged / "mmproj.gguf"
                    link.unlink(missing_ok=True)
                    link.symlink_to(projector)
                    entries.append(f"mmproj = {link}\n")
                entries.append("\n")
                ids.append(model_id)
                warn(f"registered {model_id}")
    (output / "models.ini").write_text("".join(entries))
    warn(f"{len(ids)} model(s) available; weights load on demand")
    return ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", type=Path)
    parser.add_argument("--hf-cache-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="dedicated writable directory for generated presets and symlinks")
    args = parser.parse_args()
    try:
        discover([("models", args.models_dir), ("hf", args.hf_cache_dir)], args.output_dir)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"discovery: {exc}\n")


if __name__ == "__main__":
    main()
