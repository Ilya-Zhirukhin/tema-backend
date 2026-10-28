from httpx import AsyncClient

from tests.conftest import RegisterFn
from tests.helpers import classroom_with_student, login


async def test_notes_crud_and_pinning(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    _, channel_id, student = await classroom_with_student(client, register, auth_headers)
    url = f"/api/v1/channels/{channel_id}/notes"

    resp = await client.post(url, headers=student, json={"title": "Конспект", "body": "# Лекция 1"})
    assert resp.status_code == 201
    student_note = resp.json()
    assert student_note["author"]["username"] == "student"

    # закреплять может только модератор/владелец
    resp = await client.post(url, headers=student, json={"title": "x", "pinned": True})
    assert resp.status_code == 403
    pinned = (
        await client.post(url, headers=auth_headers, json={"title": "Правила", "pinned": True})
    ).json()

    notes = (await client.get(url, headers=student)).json()
    assert [n["title"] for n in notes] == ["Правила", "Конспект"]

    resp = await client.patch(
        f"/api/v1/notes/{pinned['id']}", headers=student, json={"title": "взлом"}
    )
    assert resp.status_code == 403
    resp = await client.patch(
        f"/api/v1/notes/{student_note['id']}", headers=student, json={"body": "обновил"}
    )
    assert resp.json()["body"] == "обновил"

    # владелец удаляет чужую заметку
    resp = await client.delete(f"/api/v1/notes/{student_note['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert (
        await client.get(f"/api/v1/notes/{student_note['id']}", headers=student)
    ).status_code == 404


async def test_outsider_cannot_see_notes(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    _, channel_id, _ = await classroom_with_student(client, register, auth_headers)
    note = (
        await client.post(
            f"/api/v1/channels/{channel_id}/notes", headers=auth_headers, json={"title": "t"}
        )
    ).json()
    await register(username="outsider")
    outsider = await login(client, "outsider")
    assert (await client.get(f"/api/v1/notes/{note['id']}", headers=outsider)).status_code == 404
