from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/shop_sys"

    meta_app_secret: str = ""
    meta_verify_token: str = "changeme-random-string"
    meta_page_access_token: str = ""
    meta_ig_access_token: str = ""

    # Dedicated read-only credential for the separate history-analysis module.
    # It is deliberately never used by the Messenger sending service.
    meta_history_access_token: str = ""
    meta_history_page_id: str = ""
    meta_history_lookback_days: int = 60

    line_channel_secret: str = ""

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
