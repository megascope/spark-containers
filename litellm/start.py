"""Omit the Ollama route when no upstream is configured, then start LiteLLM."""

import os
from pathlib import Path
import sys
import tempfile

import yaml


def main():
    args = sys.argv[1:]
    if not os.environ.get("OLLAMA_API_BASE", "").strip():
        config_index = args.index("--config") + 1
        config = yaml.safe_load(Path(args[config_index]).read_text())
        config["model_list"] = [
            route for route in config["model_list"]
            if route.get("litellm_params", {}).get("api_base")
            != "os.environ/OLLAMA_API_BASE"
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", prefix="litellm-", suffix=".yaml", delete=False
        ) as output:
            yaml.safe_dump(config, output, sort_keys=False)
            args[config_index] = output.name
        print("Ollama upstream unset; Ollama routes disabled.", flush=True)

    # Preserve the upstream startup behavior, including optional tracing.
    entrypoint = "/app/docker/prod_entrypoint.sh"
    os.execv(entrypoint, [entrypoint, *args])


if __name__ == "__main__":
    main()
