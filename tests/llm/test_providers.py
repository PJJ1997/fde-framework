import os
import unittest
from unittest.mock import Mock, patch

from llm.providers.azure_openai import create_azure_openai_llm
from llm.providers.deepseek import create_deepseek_llm


class LLMProviderTests(unittest.TestCase):
    def test_azure_openai_uses_environment_configuration(self):
        expected = Mock()
        environment = {
            "AZURE_OPENAI_ENDPOINT": "https://azure.example.test",
            "AZURE_OPENAI_API_KEY": "azure-test-key",
            "AZURE_OPENAI_DEPLOYMENT": "test-deployment",
            "AZURE_OPENAI_API_VERSION": "2025-04-01-preview",
            "LLM_TEMPERATURE": "0.2",
        }
        with patch.dict(os.environ, environment, clear=True), patch(
            "llm.providers.azure_openai.AzureChatOpenAI",
            return_value=expected,
        ) as client:
            result = create_azure_openai_llm()

        self.assertIs(result, expected)
        self.assertEqual(
            client.call_args.kwargs,
            {
                "azure_endpoint": "https://azure.example.test",
                "api_key": "azure-test-key",
                "deployment_name": "test-deployment",
                "api_version": "2025-04-01-preview",
                "temperature": 0.2,
            },
        )

    def test_deepseek_uses_environment_configuration(self):
        expected = Mock()
        environment = {
            "DEEPSEEK_API_KEY": "deepseek-test-key",
            "DEEPSEEK_MODEL": "test-model",
            "DEEPSEEK_BASE_URL": "https://deepseek.example.test/v1",
            "LLM_TEMPERATURE": "0.3",
        }
        with patch.dict(os.environ, environment, clear=True), patch(
            "llm.providers.deepseek.ChatOpenAI",
            return_value=expected,
        ) as client:
            result = create_deepseek_llm()

        self.assertIs(result, expected)
        self.assertEqual(
            client.call_args.kwargs,
            {
                "model": "test-model",
                "api_key": "deepseek-test-key",
                "base_url": "https://deepseek.example.test/v1",
                "temperature": 0.3,
            },
        )

    def test_azure_openai_rejects_missing_api_key(self):
        environment = {
            "AZURE_OPENAI_ENDPOINT": "https://azure.example.test",
            "AZURE_OPENAI_DEPLOYMENT": "test-deployment",
        }
        with patch.dict(os.environ, environment, clear=True), patch(
            "llm.providers.azure_openai.load_environment",
        ):
            with self.assertRaisesRegex(
                ValueError,
                "AZURE_OPENAI_API_KEY",
            ):
                create_azure_openai_llm()

    def test_deepseek_rejects_missing_api_key(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "llm.providers.deepseek.load_environment",
        ):
            with self.assertRaisesRegex(ValueError, "DEEPSEEK_API_KEY"):
                create_deepseek_llm()


if __name__ == "__main__":
    unittest.main()
