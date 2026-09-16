from functools import lru_cache
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", env_prefix="VISIONGUARD_")

    app_name: str = "SURAKSH"
    database_url: str = "sqlite:///./visionguard.db"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 12
    public_dashboard_url: str = "http://localhost:3010"
    whatsapp_webhook_url: str | None = None
    email_webhook_url: str | None = None
    demo_seed: bool = True
    edge_ingest_key: str = ""
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3010,http://127.0.0.1:3010"
    demo_mode: bool = True
    demo_runtime_only: bool = False
    demo_media_dir: str = ""
    postgis_enabled: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
