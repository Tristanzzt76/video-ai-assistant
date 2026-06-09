from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略 .env 中未声明的变量
    )

    zhipu_api_key: str = ""
    embedding_model: str = "local"
    llm_provider: str = "zhipu"
    chroma_path: str = "./data/chroma"
    docs_path: str = "./data/docs"
    cors_origins: str = "http://localhost:3000"
    tavily_api_key: str = ""
    log_level: str = "INFO"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
