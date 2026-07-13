"""DeepSeek LLM provider."""
from langchain_openai import ChatOpenAI


def create_deepseek_llm() -> ChatOpenAI:
    """Create DeepSeek LLM instance.

    DeepSeek uses OpenAI-compatible API.
    """
    return ChatOpenAI(
        model="deepseek-chat",
        api_key="sk-0077f8cbbeff49bc8c450c1ecb5ac451",
        base_url="https://api.deepseek.com/v1",
        temperature=0.7,
    )