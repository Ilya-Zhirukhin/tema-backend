import os
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from tema.app import create_app
from tema.core.config import Settings
from tema.models import Base

ROOT = Path(__file__).parent.parent
PASSWORD = "correct-horse-battery"

type RegisterFn = Callable[..., Awaitable[dict[str, str]]]


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        env="test",
        database_url=os.getenv(
            "TEMA_TEST_DATABASE_URL", "postgresql+asyncpg://tema:tema@localhost:5432/tema_test"
        ),
        redis_url=os.getenv("TEMA_TEST_REDIS_URL", "redis://localhost:6379/15"),
        jwt_secret="test-secret-key-that-is-long-enough-for-hs256",
        metrics_enabled=False,
        log_level="WARNING",
    )


@pytest.fixture(scope="session", autouse=True)
def _migrate(settings: Settings) -> None:
    """Схему создаём настоящими миграциями: заодно проверяем, что они работают в обе стороны."""
    cfg = Config(ROOT / "alembic.ini")
    cfg.attributes["database_url"] = str(settings.database_url)
    cfg.attributes["configure_logger"] = False
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    async with LifespanManager(application):
        yield application


@pytest.fixture(autouse=True)
async def _clean(app: FastAPI) -> None:
    async with app.state.db.engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    await app.state.redis.flushdb()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://tema.test") as c:
        yield c


@pytest.fixture
def register(client: AsyncClient) -> RegisterFn:
    async def _register(
        username: str = "ivan", email: str | None = None, password: str = PASSWORD
    ) -> dict[str, str]:
        payload = {
            "email": email or f"{username}@example.com",
            "username": username,
            "first_name": "Иван",
            "last_name": "Петров",
            "password": password,
        }
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 201, resp.text
        return payload

    return _register


@pytest.fixture
async def auth_headers(client: AsyncClient, register: RegisterFn) -> dict[str, str]:
    await register()
    resp = await client.post("/api/v1/auth/login", json={"login": "ivan", "password": PASSWORD})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
