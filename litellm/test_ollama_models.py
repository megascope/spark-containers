"""Run with: python3 -m unittest discover -s litellm -p 'test_*.py'."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "ollama_models", Path(__file__).with_name("ollama-models.py")
)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class ModelExportTests(unittest.TestCase):
    def export(self, ids):
        response = json.dumps({"data": [{"id": name} for name in ids]})
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch("sys.argv", ["ollama-models.py"]),
            patch.object(helper.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, response)),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = helper.main()
        return status, stdout.getvalue(), stderr.getvalue()

    def test_wildcard_alongside_discovered_models(self):
        self.assertEqual(
            self.export(["local-llama", "ollama_chat/*", "ollama_chat/z:8b", "ollama_chat/a:3b", "ollama_chat/z:8b"]),
            (0, "export OLLAMA_MODELS=+ollama_chat/a:3b,+ollama_chat/z:8b\n", ""),
        )

    def test_wildcard_only_does_not_clear_existing_export(self):
        status, stdout, stderr = self.export(["local-llama", "ollama_chat/*"])
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertIn("no concrete models", stderr)

    def test_empty_inventory(self):
        self.assertEqual(self.export([]), (0, "export OLLAMA_MODELS=''\n", ""))

    def test_unsafe_model_name(self):
        status, stdout, stderr = self.export(["ollama_chat/$(echo unsafe)"])
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertIn("unsupported model name", stderr)


if __name__ == "__main__":
    unittest.main()
