from httpx import AsyncClient

from tests.conftest import PASSWORD, RegisterFn

REFRESH_COOKIE = "tema_refresh"


async def test_register_returns_profile_without_password(
    client: AsyncClient, register: RegisterFn
) -> None:
    await register()
    resp = await client.post("/api/v1/auth/login", json={"login": "ivan", "password": PASSWORD})
    me = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {resp.json()['access_token']}"}
    )
    body = me.json()
    assert body["username"] == "ivan"
    assert body["account_type"] == "student"
    assert body["role"] == "user"
    assert body["has_password"] is True
    assert "password" not in body
    assert "password_hash" not in body


async def test_register_duplicate_email_is_case_insensitive(
    client: AsyncClient, register: RegisterFn
) -> None:
    await register(email="Ivan@Example.com")
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "ivan@example.com",
            "username": "other",
            "first_name": "A",
            "last_name": "B",
            "password": PASSWORD,
        },
    )
    assert resp.status_code == 409
    assert resp.headers["content-type"] == "application/problem+json"
    assert resp.json()["field"] == "email"


async def test_register_duplicate_username(client: AsyncClient, register: RegisterFn) -> None:
    await register(username="ivan")
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "x@example.com",
            "username": "IVAN",
            "first_name": "A",
            "last_name": "B",
            "password": PASSWORD,
        },
    )
    assert resp.status_code == 409
    assert resp.json()["field"] == "username"


async def test_register_validation_error_is_problem_json(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "username": "a", "password": "123"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["status"] == 422
    fields = {tuple(e["loc"])[-1] for e in body["errors"]}
    assert {"email", "username", "password", "first_name", "last_name"} <= fields


async def test_login_by_email_or_username(client: AsyncClient, register: RegisterFn) -> None:
    await register()
    for login in ("ivan", "IVAN@example.com"):
        resp = await client.post("/api/v1/auth/login", json={"login": login, "password": PASSWORD})
        assert resp.status_code == 200, login
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900
        assert REFRESH_COOKIE in resp.cookies


async def test_login_wrong_password(client: AsyncClient, register: RegisterFn) -> None:
    await register()
    resp = await client.post("/api/v1/auth/login", json={"login": "ivan", "password": "nope-nope"})
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_login_unknown_user(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/login", json={"login": "ghost", "password": PASSWORD})
    assert resp.status_code == 401


async def test_oauth2_form_login_for_swagger(client: AsyncClient, register: RegisterFn) -> None:
    await register()
    resp = await client.post("/api/v1/auth/token", data={"username": "ivan", "password": PASSWORD})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_protected_route_requires_token(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/users/me")).status_code == 401
    resp = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401


async def test_refresh_token_cannot_be_used_as_access(
    client: AsyncClient, register: RegisterFn
) -> None:
    await register()
    resp = await client.post("/api/v1/auth/login", json={"login": "ivan", "password": PASSWORD})
    refresh = resp.cookies[REFRESH_COOKIE]
    me = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {refresh}"})
    assert me.status_code == 401


async def test_refresh_rotates_token(client: AsyncClient, register: RegisterFn) -> None:
    await register()
    login = await client.post("/api/v1/auth/login", json={"login": "ivan", "password": PASSWORD})
    old_refresh = login.cookies[REFRESH_COOKIE]

    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200
    assert resp.json()["access_token"]
    assert resp.cookies[REFRESH_COOKIE] != old_refresh

    # Старый refresh одноразовый: повторное использование отклоняется.
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, old_refresh)
    reused = await client.post("/api/v1/auth/refresh")
    assert reused.status_code == 401


async def test_refresh_without_cookie(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_logout_revokes_refresh(client: AsyncClient, register: RegisterFn) -> None:
    await register()
    login = await client.post("/api/v1/auth/login", json={"login": "ivan", "password": PASSWORD})
    refresh = login.cookies[REFRESH_COOKIE]

    assert (await client.post("/api/v1/auth/logout")).status_code == 204

    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, refresh)
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401


async def test_oauth_provider_not_configured(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/oauth/github/login")
    assert resp.status_code == 404
