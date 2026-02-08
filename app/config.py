from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="WATCHWHAT_",
        extra="ignore",
    )

    db_path: str = "/Users/cocodzh/.watchwhat/data/watchwhat.db"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    sync_inline: bool = False
    max_history_pages: int = 200
    request_timeout: int = 20
    persist_cookie_on_disk: bool = True
    cookie_store_path: str = "/Users/cocodzh/.watchwhat/data/cookies.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
