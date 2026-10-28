import re

from httpx import AsyncClient

from tema.core.mail import MemoryMailer
from tests.conftest import PASSWORD, RegisterFn


def token_from(mailer: MemoryMailer) -> str:
    match = re.search(r"token=([\w-]+)", mailer.outbox[-1].text)
    assert match
    return match.group(1)


async def test_reset_flow(client: AsyncClient, register: RegisterFn, mailer: MemoryMailer) -> None:
    await register()
    login = await client.post("/api/v1/auth/login", json={"login": "ivan", "password": PASSWORD})
    old_refresh = login.cookies["tema_refresh"]

    resp = await client.post(
        "/api/v1/auth/password-reset/request", json={"email": "IVAN@example.com"}
    )
    assert resp.status_code == 202
    assert len(mailer.outbox) == 1
    assert mailer.outbox[0].to == "ivan@example.com"
    token = token_from(mailer)

    resp = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "brand-new-password"},
    )
    assert resp.status_code == 204

    # ссылка одноразовая
    again = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "another-password"},
    )
    assert again.status_code == 400

    old = await client.post("/api/v1/auth/login", json={"login": "ivan", "password": PASSWORD})
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login", json={"login": "ivan", "password": "brand-new-password"}
    )
    assert new.status_code == 200

    # все прежние сессии отозваны
    client.cookies.clear()
    client.cookies.set("tema_refresh", old_refresh)
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_unknown_email_gives_same_answer(client: AsyncClient, mailer: MemoryMailer) -> None:
    resp = await client.post(
        "/api/v1/auth/password-reset/request", json={"email": "ghost@example.com"}
    )
    assert resp.status_code == 202
    assert mailer.outbox == []


async def test_bad_token(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": "x" * 43, "new_password": "brand-new-password"},
    )
    assert resp.status_code == 400
    assert resp.json()["type"].endswith("/invalid_reset_token")


async def test_login_rate_limit(client: AsyncClient, register: RegisterFn) -> None:
    await register()
    for _ in range(10):
        resp = await client.post("/api/v1/auth/login", json={"login": "ivan", "password": "bad"})
        assert resp.status_code == 401
    resp = await client.post("/api/v1/auth/login", json={"login": "ivan", "password": PASSWORD})
    assert resp.status_code == 429
    assert int(resp.headers["retry-after"]) > 0


async def test_password_reset_rate_limit(client: AsyncClient) -> None:
    for _ in range(3):
        await client.post("/api/v1/auth/password-reset/request", json={"email": "a@b.ru"})
    resp = await client.post("/api/v1/auth/password-reset/request", json={"email": "a@b.ru"})
    assert resp.status_code == 429
