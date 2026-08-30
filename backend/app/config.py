from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/sstore"

    meta_app_secret: str = ""
    meta_app_id: str = ""
    meta_verify_token: str = "changeme-random-string"
    meta_page_access_token: str = ""
    meta_ig_access_token: str = ""
    # OAuth is optional until the app is ready for Page self-service onboarding.
    # Generate META_TOKEN_ENCRYPTION_KEY with Fernet.generate_key().decode().
    meta_oauth_redirect_uri: str = ""
    meta_oauth_frontend_url: str = ""
    # OAuth callback always returns here; defaults to the standard onboarding page.
    meta_oauth_login_frontend_url: str = ""
    # Public web origin used by the Data Deletion Callback response URL.
    meta_public_web_url: str = ""
    meta_token_encryption_key: str = ""
    # Optional in development; production uses this to distribute Inbox events
    # to every backend instance serving an SSE connection.
    redis_url: str = ""

    # Dedicated read-only credential for the separate history-analysis module.
    # It is deliberately never used by the Messenger sending service.
    meta_history_access_token: str = ""
    meta_history_page_id: str = ""
    meta_history_lookback_days: int = 60

    line_channel_secret: str = ""

    # Capacitor Android serves its bundled frontend from http://localhost.
    # It is a fixed WebView origin, not a LAN wildcard.
    cors_origins: str = "http://localhost:3000,http://localhost,capacitor://localhost"
    # Development may be accessed with localhost or this computer's current
    # private-LAN address.  Do not hard-code a single address because it changes
    # when the computer is moved to another network.
    cors_origin_regex: str = (
        r"^(?:http://(localhost|127\.0\.0\.1|"
        r"10(?:\.\d{1,3}){3}|"
        r"192\.168(?:\.\d{1,3}){2}|"
        r"172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}):3000"
        r"|https://[a-z0-9-]+\.trycloudflare\.com)$"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
