from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_host: str = "0.0.0.0"
    app_port: int = 8000

    llm_provider: str = "openrouter"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4.1"
    openrouter_site_url: str = "https://fest.bupcopc.tech"
    openrouter_app_name: str = "GridWise-LLM"
    llm_timeout_seconds: float = 20.0
    llm_max_retries: int = 2
    llm_max_tokens: int = 2000


@lru_cache
def get_settings() -> Settings:
    return Settings()
