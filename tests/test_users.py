from httpx import AsyncClient
from sqlalchemy import update

from tema.modules.users.models import Role, User
from tests.conftest import PASSWORD, RegisterFn


async def login(client: AsyncClient, login: str, password: str = PASSWORD) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/login", json={"login": login, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_update_profile(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers,
        json={"first_name": "  Илья  ", "username": "ilya"},
    )
    assert resp.status_code == 200
    assert resp.json()["first_name"] == "Илья"
    assert resp.json()["username"] == "ilya"


async def test_update_username_conflict(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    await register(username="taken")
    resp = await client.patch("/api/v1/users/me", headers=auth_headers, json={"username": "Taken"})
    assert resp.status_code == 409


async def test_change_password_revokes_sessions(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.put(
        "/api/v1/users/me/password",
        headers=auth_headers,
        json={"current_password": "wrong-password", "new_password": "new-password-123"},
    )
    assert resp.status_code == 401

    resp = await client.put(
        "/api/v1/users/me/password",
        headers=auth_headers,
        json={"current_password": PASSWORD, "new_password": "new-password-123"},
    )
    assert resp.status_code == 204

    # refresh-cookie, полученный до смены пароля, больше не работает
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    await login(client, "ivan", "new-password-123")


async def test_search_and_public_profile(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    await register(username="maria")
    await register(username="marat")

    resp = await client.get("/api/v1/users", params={"q": "MAR"}, headers=auth_headers)
    page = resp.json()
    assert page["total"] == 2
    assert [u["username"] for u in page["items"]] == ["marat", "maria"]
    assert "email" not in page["items"][0]

    user_id = page["items"][0]["id"]
    resp = await client.get(f"/api/v1/users/{user_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "marat"


async def test_search_pagination(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    for i in range(3):
        await register(username=f"user{i}")
    resp = await client.get("/api/v1/users", params={"limit": 2, "offset": 2}, headers=auth_headers)
    page = resp.json()
    assert page["total"] == 4  # + ivan
    assert len(page["items"]) == 2


async def test_unknown_user_returns_404(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.get(
        "/api/v1/users/01900000-0000-7000-8000-000000000000", headers=auth_headers
    )
    assert resp.status_code == 404
    assert resp.json()["type"].endswith("/not_found")


async def test_delete_me(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    assert (await client.delete("/api/v1/users/me", headers=auth_headers)).status_code == 204
    assert (await client.get("/api/v1/users/me", headers=auth_headers)).status_code == 401
    resp = await client.post("/api/v1/auth/login", json={"login": "ivan", "password": PASSWORD})
    assert resp.status_code == 401


async def test_only_admin_can_change_roles(
    app, client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    await register(username="boss")
    boss_headers = await login(client, "boss")
    me = (await client.get("/api/v1/users/me", headers=auth_headers)).json()

    resp = await client.put(
        f"/api/v1/users/{me['id']}/role", headers=boss_headers, json={"role": "admin"}
    )
    assert resp.status_code == 403

    async with app.state.db.sessionmaker() as session:
        await session.execute(update(User).where(User.username == "boss").values(role=Role.ADMIN))
        await session.commit()

    resp = await client.put(
        f"/api/v1/users/{me['id']}/role", headers=boss_headers, json={"role": "admin"}
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"
