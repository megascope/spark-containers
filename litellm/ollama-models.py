#!/usr/bin/env python3
"""Print an OLLAMA_MODELS export from the running LiteLLM service's model list."""

import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys


# Execute inside LiteLLM so authentication and networking use its environment.
QUERY = """
import os
import sys
import urllib.request

request = urllib.request.Request(
    "http://127.0.0.1:4000/v1/models",
    headers={"Authorization": "Bearer " + os.environ["LITELLM_MASTER_KEY"]},
)
with urllib.request.urlopen(request, timeout=30) as response:
    sys.stdout.write(response.read().decode("utf-8"))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    try:
        wrapper = Path(__file__).resolve().parents[1] / "compose.sh"
        result = subprocess.run(
            [str(wrapper), "litellm", "exec", "-T", "litellm", "python", "-c", QUERY],
            stdout=subprocess.PIPE, text=True, check=True, timeout=45,
        )
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("expected a LiteLLM response containing a data list")

        names = set()
        saw_wildcard = False
        for entry in payload["data"]:
            name = entry.get("id") if isinstance(entry, dict) else None
            if not isinstance(name, str):
                raise ValueError("model entry is missing a string id")
            if not name.startswith("ollama_chat/"):
                continue
            # LiteLLM can include routing patterns alongside discovered model IDs.
            if "*" in name:
                saw_wildcard = True
                continue
            # Reject NextChat list/alias syntax and shell metacharacters in model names.
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]*", name):
                raise ValueError(f"unsupported model name: {name!r}")
            names.add(name)
        if saw_wildcard and not names:
            raise ValueError(
                "LiteLLM returned only Ollama wildcard routes, with no concrete models. "
                "Check check_provider_endpoint: true in litellm/config.yaml, restart "
                "LiteLLM, and check its logs and connectivity to Ollama."
            )
        models = ",".join("+" + name for name in sorted(names))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ollama-models: {exc}", file=sys.stderr)
        return 1

    print("export OLLAMA_MODELS=" + shlex.quote(models))
    return 0


if __name__ == "__main__":
    sys.exit(main())
