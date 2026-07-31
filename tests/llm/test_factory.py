import os
import unittest
from unittest.mock import Mock, patch

from llm.factory import create_llm


class LLMFactoryTests(unittest.TestCase):
    def test_environment_selects_default_provider(self):
        expected = Mock()
        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "deepseek"},
            clear=True,
        ), patch(
            "llm.providers.deepseek.create_deepseek_llm",
            return_value=expected,
        ):
            self.assertIs(create_llm(), expected)

    def test_explicit_provider_overrides_environment(self):
        expected = Mock()
        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "deepseek"},
            clear=True,
        ), patch(
            "llm.providers.azure_openai.create_azure_openai_llm",
            return_value=expected,
        ):
            self.assertIs(create_llm("azure_openai"), expected)


if __name__ == "__main__":
    unittest.main()
