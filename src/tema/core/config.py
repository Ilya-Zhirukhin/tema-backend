from datetime import timedelta
from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Все настройки приложения читаются из переменных окружения с префиксом TEMA_.

    Секретов по умолчанию нет: без TEMA_JWT_SECRET приложение не стартует.
    """

    model_config = SettingsConfigDict(
        env_prefix="TEMA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["local", "test", "production"] = "local"
    app_name: str = "Tema API"
    host: str = "0.0.0.0"  # noqa: S104 - внутри контейнера слушаем все интерфейсы
    port: int = 8000

    database_url: PostgresDsn = PostgresDsn("postgresql+asyncpg://tema:tema@localhost:5432/tema")
    database_echo: bool = False
    database_pool_size: int = 10
    database_max_overflow: int = 10

    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")

    jwt_secret: SecretStr
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_ttl: timedelta = timedelta(minutes=15)
    refresh_token_ttl: timedelta = timedelta(days=30)
    refresh_cookie_name: str = "tema_refresh"
    session_secret: SecretStr | None = None

    cors_origins: list[str] = []
    frontend_url: AnyHttpUrl = AnyHttpUrl("http://localhost:5173")

    github_client_id: str | None = None
    github_client_secret: SecretStr | None = None
    yandex_client_id: str | None = None
    yandex_client_secret: SecretStr | None = None

    log_level: str = "INFO"
    log_json: bool = False

    otel_enabled: bool = False
    otel_service_name: str = "tema-api"
    otel_exporter_endpoint: str = "http://localhost:4318/v1/traces"

    metrics_enabled: bool = True

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # значения приходят из окружения
