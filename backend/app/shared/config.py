from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Personal Memory AI"
    environment: str = "development"
    database_url: str = "sqlite:///./memory.sqlite3"
    test_database_url: str = "sqlite:///./test.sqlite3"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 1440
    auto_create_admin: bool = True
    admin_username: str = "admin"
    admin_password: str = ""
    admin_display_name: str = "系统管理员"
    openai_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    openai_api_key: str = ""
    chat_model: str = "qwen-max"
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1536
    auto_extract_memory: bool = True
    cors_origins: str = "http://localhost:8080,http://localhost:5173"
    memory_export_dir: str = "./data/memories"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
