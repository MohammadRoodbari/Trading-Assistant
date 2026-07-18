
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from config.settings import settings

def load_chat_model(
    model_name: str = settings.LLM_MODEL,
    provider_url: str = settings.BASE_URL,
    api_key: str = settings.API_KEY,
) -> BaseChatModel:
    """Load an OpenAI-compatible chat model"""

    return ChatOpenAI(
        model=model_name,
        base_url=provider_url,
        api_key=api_key,
        temperature=0
    )