"""Omit optional routes without configured upstreams, then start LiteLLM."""

import os
from pathlib import Path
import sys
import tempfile


def enabled_routes(config, env):
    disabled = {f"os.environ/{name}" for name in ("OLLAMA_API_BASE", "VLLM_API_BASE")
                if not env.get(name, "").strip()}
    config["model_list"] = [route for route in config["model_list"]
                            if route.get("litellm_params", {}).get("api_base") not in disabled]
    return config


def main():
    import yaml

    args = sys.argv[1:]
    if any(not os.environ.get(name, "").strip() for name in ("OLLAMA_API_BASE", "VLLM_API_BASE")):
        config_index = args.index("--config") + 1
        config = yaml.safe_load(Path(args[config_index]).read_text())
        config = enabled_routes(config, os.environ)
        with tempfile.NamedTemporaryFile(
            mode="w", prefix="litellm-", suffix=".yaml", delete=False
        ) as output:
            yaml.safe_dump(config, output, sort_keys=False)
            args[config_index] = output.name
        print("Optional upstream routes filtered by configuration.", flush=True)

    # Preserve the upstream startup behavior, including optional tracing.
    entrypoint = "/app/docker/prod_entrypoint.sh"
    os.execv(entrypoint, [entrypoint, *args])


if __name__ == "__main__":
    main()
