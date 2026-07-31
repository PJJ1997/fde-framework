"""Azure OpenAI LLM provider."""
from langchain_openai import AzureChatOpenAI

from ..config import get_env, get_float_env, load_environment


def create_azure_openai_llm() -> AzureChatOpenAI:
    """Create Azure OpenAI LLM instance.
    
    Uses Azure OpenAI configuration from the environment.
    """
    load_environment()
    return AzureChatOpenAI(
        azure_endpoint=get_env("AZURE_OPENAI_ENDPOINT", required=True),
        api_key=get_env("AZURE_OPENAI_API_KEY", required=True),
        deployment_name=get_env(
            "AZURE_OPENAI_DEPLOYMENT",
            required=True,
        ),
        api_version=get_env(
            "AZURE_OPENAI_API_VERSION",
            "2025-04-01-preview",
        ),
        temperature=get_float_env("LLM_TEMPERATURE", 0.7),
    )
