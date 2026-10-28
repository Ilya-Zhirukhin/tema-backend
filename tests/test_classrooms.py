from httpx import AsyncClient

from tests.conftest import PASSWORD, RegisterFn


async def login(client: AsyncClient, username: str) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/login", json={"login": username, "password": PASSWORD})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def user(client: AsyncClient, register: RegisterFn, username: str) -> dict[str, str]:
    await register(username=username)
    return await login(client, username)


async def create(client: AsyncClient, headers: dict[str, str], name: str = "Матан") -> dict:
    resp = await client.post(
        "/api/v1/classrooms", headers=headers, json={"name": name, "description": "1 курс"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def join(client: AsyncClient, headers: dict[str, str], code: str) -> None:
    resp = await client.post("/api/v1/classrooms/join", headers=headers, json={"code": code})
    assert resp.status_code == 200, resp.text


async def me_id(client: AsyncClient, headers: dict[str, str]) -> str:
    return (await client.get("/api/v1/users/me", headers=headers)).json()["id"]


async def test_create_makes_owner_and_general_channel(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    room = await create(client, auth_headers)
    assert room["role"] == "owner"
    assert len(room["invite_code"]) == 8

    channels = (
        await client.get(f"/api/v1/classrooms/{room['id']}/channels", headers=auth_headers)
    ).json()
    assert [c["name"] for c in channels] == ["General"]

    mine = (await client.get("/api/v1/classrooms", headers=auth_headers)).json()
    assert [r["id"] for r in mine] == [room["id"]]


async def test_join_by_code(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    room = await create(client, auth_headers)
    student = await user(client, register, "student")

    resp = await client.post(
        "/api/v1/classrooms/join", headers=student, json={"code": room["invite_code"].lower()}
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "member"
    assert resp.json()["invite_code"] is None  # обычный участник код не видит

    again = await client.post(
        "/api/v1/classrooms/join", headers=student, json={"code": room["invite_code"]}
    )
    assert again.status_code == 409

    members = (await client.get(f"/api/v1/classrooms/{room['id']}/members", headers=student)).json()
    assert {m["user"]["username"]: m["role"] for m in members} == {
        "ivan": "owner",
        "student": "member",
    }


async def test_invalid_code(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.post(
        "/api/v1/classrooms/join", headers=auth_headers, json={"code": "NOPE1234"}
    )
    assert resp.status_code == 404


async def test_outsider_sees_404(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    room = await create(client, auth_headers)
    outsider = await user(client, register, "outsider")
    for path in ("", "/members", "/channels"):
        resp = await client.get(f"/api/v1/classrooms/{room['id']}{path}", headers=outsider)
        assert resp.status_code == 404, path


async def test_regenerate_code_invalidates_old(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    room = await create(client, auth_headers)
    resp = await client.post(f"/api/v1/classrooms/{room['id']}/invite-code", headers=auth_headers)
    new_code = resp.json()["invite_code"]
    assert new_code != room["invite_code"]

    student = await user(client, register, "student")
    old = await client.post(
        "/api/v1/classrooms/join", headers=student, json={"code": room["invite_code"]}
    )
    assert old.status_code == 404
    await join(client, student, new_code)


async def test_member_cannot_manage(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    room = await create(client, auth_headers)
    student = await user(client, register, "student")
    await join(client, student, room["invite_code"])
    rid = room["id"]

    checks = [
        client.patch(f"/api/v1/classrooms/{rid}", headers=student, json={"name": "x"}),
        client.delete(f"/api/v1/classrooms/{rid}", headers=student),
        client.post(f"/api/v1/classrooms/{rid}/invite-code", headers=student),
        client.post(f"/api/v1/classrooms/{rid}/channels", headers=student, json={"name": "x"}),
    ]
    for coro in checks:
        assert (await coro).status_code == 403


async def test_owner_promotes_moderator_who_manages_channels(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    room = await create(client, auth_headers)
    rid = room["id"]
    mod = await user(client, register, "mod")
    await join(client, mod, room["invite_code"])
    mod_id = await me_id(client, mod)

    resp = await client.put(
        f"/api/v1/classrooms/{rid}/members/{mod_id}/role",
        headers=auth_headers,
        json={"role": "moderator"},
    )
    assert resp.json() == {"role": "moderator"}

    resp = await client.post(
        f"/api/v1/classrooms/{rid}/channels", headers=mod, json={"name": "Домашки"}
    )
    assert resp.status_code == 201
    channel_id = resp.json()["id"]

    dup = await client.post(
        f"/api/v1/classrooms/{rid}/channels", headers=mod, json={"name": "General"}
    )
    assert dup.status_code == 409

    renamed = await client.patch(f"/api/v1/channels/{channel_id}", headers=mod, json={"name": "ДЗ"})
    assert renamed.json()["name"] == "ДЗ"
    assert (await client.delete(f"/api/v1/channels/{channel_id}", headers=mod)).status_code == 204


async def test_cannot_delete_last_channel(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    room = await create(client, auth_headers)
    channels = (
        await client.get(f"/api/v1/classrooms/{room['id']}/channels", headers=auth_headers)
    ).json()
    resp = await client.delete(f"/api/v1/channels/{channels[0]['id']}", headers=auth_headers)
    assert resp.status_code == 409


async def test_owner_cannot_be_made_twice_or_change_self(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    room = await create(client, auth_headers)
    rid = room["id"]
    student = await user(client, register, "student")
    await join(client, student, room["invite_code"])
    sid = await me_id(client, student)
    oid = await me_id(client, auth_headers)

    resp = await client.put(
        f"/api/v1/classrooms/{rid}/members/{sid}/role",
        headers=auth_headers,
        json={"role": "owner"},
    )
    assert resp.status_code == 403
    resp = await client.put(
        f"/api/v1/classrooms/{rid}/members/{oid}/role",
        headers=auth_headers,
        json={"role": "member"},
    )
    assert resp.status_code == 403


async def test_leave_and_kick(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    room = await create(client, auth_headers)
    rid = room["id"]
    a = await user(client, register, "alice")
    b = await user(client, register, "bob")
    await join(client, a, room["invite_code"])
    await join(client, b, room["invite_code"])
    a_id, b_id = await me_id(client, a), await me_id(client, b)
    owner_id = await me_id(client, auth_headers)

    # участник не может выгнать другого участника и владельца
    assert (
        await client.delete(f"/api/v1/classrooms/{rid}/members/{b_id}", headers=a)
    ).status_code == 403
    assert (
        await client.delete(f"/api/v1/classrooms/{rid}/members/{owner_id}", headers=a)
    ).status_code == 403

    # сам выйти может
    assert (
        await client.delete(f"/api/v1/classrooms/{rid}/members/{a_id}", headers=a)
    ).status_code == 204
    assert (await client.get(f"/api/v1/classrooms/{rid}", headers=a)).status_code == 404

    # владелец исключает
    assert (
        await client.delete(f"/api/v1/classrooms/{rid}/members/{b_id}", headers=auth_headers)
    ).status_code == 204

    # владелец выйти не может
    assert (
        await client.delete(f"/api/v1/classrooms/{rid}/members/{owner_id}", headers=auth_headers)
    ).status_code == 403


async def test_update_and_delete_classroom(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    room = await create(client, auth_headers)
    rid = room["id"]
    resp = await client.patch(
        f"/api/v1/classrooms/{rid}",
        headers=auth_headers,
        json={"name": "Линал", "description": None},
    )
    assert resp.json()["name"] == "Линал"
    assert resp.json()["description"] is None

    assert (
        await client.delete(f"/api/v1/classrooms/{rid}", headers=auth_headers)
    ).status_code == 204
    assert (await client.get(f"/api/v1/classrooms/{rid}", headers=auth_headers)).status_code == 404


async def test_deleting_user_removes_membership(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    room = await create(client, auth_headers)
    student = await user(client, register, "student")
    await join(client, student, room["invite_code"])
    await client.delete("/api/v1/users/me", headers=student)

    members = (
        await client.get(f"/api/v1/classrooms/{room['id']}/members", headers=auth_headers)
    ).json()
    assert [m["user"]["username"] for m in members] == ["ivan"]
