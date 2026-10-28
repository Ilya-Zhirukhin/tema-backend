from fastapi import FastAPI

from tema.modules.users.models import User
from tema.modules.users.service import UserService
from tests.conftest import RegisterFn


async def oauth_login(app: FastAPI, **overrides: str | None) -> User:
    profile = {
        "provider": "github",
        "account_id": "42",
        "email": None,
        "username": "ivan",
        "first_name": "Ivan",
        "last_name": "Petrov",
        "avatar_url": None,
    } | overrides
    async with app.state.db.sessionmaker() as session:
        return await UserService(session).get_or_create_from_oauth(**profile)


async def test_creates_user_with_free_username(app: FastAPI, register: RegisterFn) -> None:
    await register(username="ivan")
    user = await oauth_login(app)
    assert user.username == "ivan_2"
    assert user.password_hash is None
    assert user.email == "github-42@users.noreply.tema"


async def test_same_provider_account_returns_same_user(app: FastAPI) -> None:
    first = await oauth_login(app)
    second = await oauth_login(app, username="renamed")
    assert first.id == second.id


async def test_links_to_existing_user_by_verified_email(app: FastAPI, register: RegisterFn) -> None:
    await register(username="ivan", email="ivan@example.com")
    user = await oauth_login(app, provider="yandex", account_id="7", email="IVAN@example.com")
    assert user.username == "ivan"
    assert user.password_hash is not None
