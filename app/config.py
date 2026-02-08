from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


_DEFAULT_DATA_DIR = Path.home() / ".watchwhat" / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="WATCHWHAT_",
        extra="ignore",
    )

    db_path: str = str(_DEFAULT_DATA_DIR / "watchwhat.db")
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    sync_inline: bool = False
    max_history_pages: int = 200
    request_timeout: int = 20
    persist_cookie_on_disk: bool = True
    cookie_store_path: str = str(_DEFAULT_DATA_DIR / "cookies.json")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
