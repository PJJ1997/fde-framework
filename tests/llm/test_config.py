import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm.config import get_env, get_float_env, load_environment


class LLMConfigTests(unittest.TestCase):
    def test_load_environment_reads_file_without_overriding_process_values(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "FROM_FILE=file-value\nEXISTING=file-value\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"EXISTING": "process-value"},
                clear=True,
            ):
                load_environment(env_path)

                self.assertEqual(os.environ["FROM_FILE"], "file-value")
                self.assertEqual(os.environ["EXISTING"], "process-value")

    def test_get_env_rejects_missing_required_value(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                ValueError,
                "AZURE_OPENAI_API_KEY",
            ):
                get_env("AZURE_OPENAI_API_KEY", required=True)

    def test_get_float_env_rejects_invalid_number(self):
        with patch.dict(
            os.environ,
            {"LLM_TEMPERATURE": "not-a-number"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "LLM_TEMPERATURE"):
                get_float_env("LLM_TEMPERATURE", 0.7)


if __name__ == "__main__":
    unittest.main()
