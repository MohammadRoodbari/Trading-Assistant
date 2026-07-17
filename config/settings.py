from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_KEY: str
    BASE_URL: str
    LLM_MODEL: str

    WEBSEARCH_MCP_URL: str
    TRADINGVIEW_MCP_URL: str
    TSETMC_MCP_URL: str

    class Config:
        env_file = ".env"


settings = Settings()
