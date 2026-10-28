from httpx import AsyncClient

from tests.conftest import PASSWORD, RegisterFn


async def login(client: AsyncClient, username: str) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/login", json={"login": username, "password": PASSWORD})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def setup_room(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> tuple[str, str, dict[str, str]]:
    """Команда ivan (владелец) + участник student. Возвращает (room_id, channel_id, student)."""
    room = (
        await client.post("/api/v1/classrooms", headers=auth_headers, json={"name": "Матан"})
    ).json()
    await register(username="student")
    student = await login(client, "student")
    await client.post(
        "/api/v1/classrooms/join", headers=student, json={"code": room["invite_code"]}
    )
    channels = (
        await client.get(f"/api/v1/classrooms/{room['id']}/channels", headers=auth_headers)
    ).json()
    return room["id"], channels[0]["id"], student


async def post(client: AsyncClient, headers: dict[str, str], channel_id: str, text: str, **kw):
    resp = await client.post(
        f"/api/v1/channels/{channel_id}/messages", headers=headers, json={"content": text, **kw}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_post_and_paginate(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    _, channel_id, student = await setup_room(client, register, auth_headers)
    for i in range(5):
        await post(client, student if i % 2 else auth_headers, channel_id, f"msg {i}")

    url = f"/api/v1/channels/{channel_id}/messages"
    page1 = (await client.get(url, headers=student, params={"limit": 3})).json()
    assert [m["content"] for m in page1] == ["msg 4", "msg 3", "msg 2"]
    assert page1[1]["author"]["username"] == "student"

    page2 = (
        await client.get(url, headers=student, params={"limit": 3, "before": page1[-1]["id"]})
    ).json()
    assert [m["content"] for m in page2] == ["msg 1", "msg 0"]


async def test_threads(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    _, channel_id, student = await setup_room(client, register, auth_headers)
    root = await post(client, auth_headers, channel_id, "Вопрос по ДЗ")
    reply = await post(client, student, channel_id, "Ответ", parent_id=root["id"])
    assert reply["parent_id"] == root["id"]

    feed = (await client.get(f"/api/v1/channels/{channel_id}/messages", headers=student)).json()
    assert [m["id"] for m in feed] == [root["id"]]  # ответы не засоряют ленту

    replies = (await client.get(f"/api/v1/messages/{root['id']}/replies", headers=student)).json()
    assert [m["content"] for m in replies] == ["Ответ"]

    # треды одноуровневые
    resp = await client.post(
        f"/api/v1/channels/{channel_id}/messages",
        headers=student,
        json={"content": "x", "parent_id": reply["id"]},
    )
    assert resp.status_code == 400


async def test_edit_and_delete_permissions(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    _, channel_id, student = await setup_room(client, register, auth_headers)
    owners_msg = await post(client, auth_headers, channel_id, "от владельца")
    students_msg = await post(client, student, channel_id, "от студента")

    resp = await client.patch(
        f"/api/v1/messages/{owners_msg['id']}", headers=student, json={"content": "взлом"}
    )
    assert resp.status_code == 403
    resp = await client.patch(
        f"/api/v1/messages/{students_msg['id']}", headers=student, json={"content": "исправил"}
    )
    assert resp.json()["content"] == "исправил"
    assert resp.json()["edited_at"] is not None

    assert (
        await client.delete(f"/api/v1/messages/{owners_msg['id']}", headers=student)
    ).status_code == 403
    # владелец (модератор+) удаляет чужое
    assert (
        await client.delete(f"/api/v1/messages/{students_msg['id']}", headers=auth_headers)
    ).status_code == 204


async def test_outsider_cannot_read_or_post(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    _, channel_id, _ = await setup_room(client, register, auth_headers)
    msg = await post(client, auth_headers, channel_id, "секрет")
    await register(username="outsider")
    outsider = await login(client, "outsider")

    url = f"/api/v1/channels/{channel_id}/messages"
    assert (await client.get(url, headers=outsider)).status_code == 404
    assert (await client.post(url, headers=outsider, json={"content": "hi"})).status_code == 404
    assert (
        await client.get(f"/api/v1/messages/{msg['id']}/replies", headers=outsider)
    ).status_code == 404


async def test_deleted_author_keeps_history(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    _, channel_id, student = await setup_room(client, register, auth_headers)
    await post(client, student, channel_id, "до свидания")
    await client.delete("/api/v1/users/me", headers=student)

    feed = (
        await client.get(f"/api/v1/channels/{channel_id}/messages", headers=auth_headers)
    ).json()
    assert feed[0]["content"] == "до свидания"
    assert feed[0]["author"] is None


async def test_direct_messages(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    await register(username="maria")
    await register(username="petr")
    maria = await login(client, "maria")
    petr = await login(client, "petr")
    ivan_id = (await client.get("/api/v1/users/me", headers=auth_headers)).json()["id"]
    maria_id = (await client.get("/api/v1/users/me", headers=maria)).json()["id"]

    for text in ("привет", "как дела?"):
        resp = await client.post(f"/api/v1/dm/{ivan_id}", headers=maria, json={"content": text})
        assert resp.status_code == 201
    await client.post(f"/api/v1/dm/{ivan_id}", headers=petr, json={"content": "йо"})
    await client.post(f"/api/v1/dm/{maria_id}", headers=auth_headers, json={"content": "норм"})

    convs = (await client.get("/api/v1/dm", headers=auth_headers)).json()
    assert [(c["peer"]["username"], c["last_message"]["content"], c["unread"]) for c in convs] == [
        ("maria", "норм", 2),
        ("petr", "йо", 1),
    ]

    history = (await client.get(f"/api/v1/dm/{maria_id}", headers=auth_headers)).json()
    assert [m["content"] for m in history] == ["норм", "как дела?", "привет"]

    assert (
        await client.post(f"/api/v1/dm/{maria_id}/read", headers=auth_headers)
    ).status_code == 204
    convs = (await client.get("/api/v1/dm", headers=auth_headers)).json()
    assert {c["peer"]["username"]: c["unread"] for c in convs} == {"maria": 0, "petr": 1}

    # переписка maria–ivan не видна petr
    assert (await client.get(f"/api/v1/dm/{maria_id}", headers=petr)).json() == []


async def test_dm_to_self_or_unknown(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    me = (await client.get("/api/v1/users/me", headers=auth_headers)).json()["id"]
    resp = await client.post(f"/api/v1/dm/{me}", headers=auth_headers, json={"content": "я"})
    assert resp.status_code == 400
    resp = await client.post(
        "/api/v1/dm/01900000-0000-7000-8000-000000000000",
        headers=auth_headers,
        json={"content": "?"},
    )
    assert resp.status_code == 404
