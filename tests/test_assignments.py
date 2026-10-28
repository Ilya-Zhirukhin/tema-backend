from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from tests.conftest import RegisterFn
from tests.helpers import classroom_with_student, login


def iso(delta: timedelta) -> str:
    return (datetime.now(UTC) + delta).isoformat()


async def make_assignment(
    client: AsyncClient, teacher: dict[str, str], channel_id: str, **overrides: object
) -> dict:
    payload = {"title": "ДЗ 1", "description": "Решить 1-5", "due_at": iso(timedelta(days=3))}
    resp = await client.post(
        f"/api/v1/channels/{channel_id}/assignments",
        headers=teacher,
        json=payload | overrides,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_only_teacher_creates(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    _, channel_id, student = await classroom_with_student(client, register, auth_headers)
    resp = await client.post(
        f"/api/v1/channels/{channel_id}/assignments",
        headers=student,
        json={"title": "x", "due_at": iso(timedelta(days=1))},
    )
    assert resp.status_code == 403

    resp = await client.post(
        f"/api/v1/channels/{channel_id}/assignments",
        headers=auth_headers,
        json={"title": "x", "due_at": "2030-01-01T10:00:00"},
    )
    assert resp.status_code == 422  # дедлайн без часового пояса


async def test_submit_with_file_grade_and_download(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    _, channel_id, student = await classroom_with_student(client, register, auth_headers)
    task = await make_assignment(client, auth_headers, channel_id, max_score=10)
    url = f"/api/v1/assignments/{task['id']}/submission"

    resp = await client.put(url, headers=student, data={"text": "  "})
    assert resp.status_code == 400  # ни текста, ни файла

    resp = await client.put(
        url,
        headers=student,
        data={"text": "Готово"},
        files={"file": ("../../etc/solution.pdf", b"%PDF-1.7 v1", "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    sub = resp.json()
    assert sub["is_late"] is False
    assert sub["file"] == {"name": "solution.pdf", "content_type": "application/pdf", "size": 11}

    # пересдача заменяет файл
    resp = await client.put(
        url, headers=student, files={"file": ("solution.pdf", b"%PDF-1.7 v2", "application/pdf")}
    )
    assert resp.json()["id"] == sub["id"]

    my = (await client.get(url, headers=student)).json()
    assert my["text"] == ""

    subs = (
        await client.get(f"/api/v1/assignments/{task['id']}/submissions", headers=auth_headers)
    ).json()
    assert [s["student"]["username"] for s in subs] == ["student"]
    assert (
        await client.get(f"/api/v1/assignments/{task['id']}/submissions", headers=student)
    ).status_code == 403

    file_resp = await client.get(f"/api/v1/submissions/{sub['id']}/file", headers=auth_headers)
    assert file_resp.status_code == 200
    assert file_resp.content == b"%PDF-1.7 v2"
    assert "solution.pdf" in file_resp.headers["content-disposition"]

    grade_url = f"/api/v1/submissions/{sub['id']}/grade"
    assert (
        await client.put(grade_url, headers=auth_headers, json={"score": 11})
    ).status_code == 400
    assert (await client.put(grade_url, headers=student, json={"score": 10})).status_code == 403
    graded = (
        await client.put(grade_url, headers=auth_headers, json={"score": 9, "feedback": "Молодец"})
    ).json()
    assert graded["score"] == 9
    assert graded["graded_at"] is not None

    # после оценки пересдать нельзя
    resp = await client.put(url, headers=student, data={"text": "ещё"})
    assert resp.status_code == 409


async def test_other_student_cannot_see_submission_file(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    room_id, channel_id, student = await classroom_with_student(client, register, auth_headers)
    task = await make_assignment(client, auth_headers, channel_id)
    sub = (
        await client.put(
            f"/api/v1/assignments/{task['id']}/submission",
            headers=student,
            files={"file": ("a.txt", b"answer", "text/plain")},
        )
    ).json()

    code = (await client.get(f"/api/v1/classrooms/{room_id}", headers=auth_headers)).json()[
        "invite_code"
    ]
    await register(username="classmate")
    classmate = await login(client, "classmate")
    await client.post("/api/v1/classrooms/join", headers=classmate, json={"code": code})

    resp = await client.get(f"/api/v1/submissions/{sub['id']}/file", headers=classmate)
    assert resp.status_code == 404
    resp = await client.get(f"/api/v1/submissions/{sub['id']}/file", headers=student)
    assert resp.status_code == 200


async def test_file_too_large(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    _, channel_id, student = await classroom_with_student(client, register, auth_headers)
    task = await make_assignment(client, auth_headers, channel_id)
    resp = await client.put(
        f"/api/v1/assignments/{task['id']}/submission",
        headers=student,
        files={"file": ("big.bin", b"x" * (1024 * 1024 + 1), "application/octet-stream")},
    )
    assert resp.status_code == 413


async def test_late_submission_and_upcoming_deadlines(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    _, channel_id, student = await classroom_with_student(client, register, auth_headers)
    overdue = await make_assignment(
        client, auth_headers, channel_id, title="Просрочено", due_at=iso(timedelta(days=-1))
    )
    await make_assignment(
        client, auth_headers, channel_id, title="Через неделю", due_at=iso(timedelta(days=7))
    )
    await make_assignment(
        client, auth_headers, channel_id, title="Завтра", due_at=iso(timedelta(days=1))
    )

    late = (
        await client.put(
            f"/api/v1/assignments/{overdue['id']}/submission",
            headers=student,
            data={"text": "сорри"},
        )
    ).json()
    assert late["is_late"] is True

    upcoming = (await client.get("/api/v1/assignments/upcoming", headers=student)).json()
    assert [a["title"] for a in upcoming] == ["Завтра", "Через неделю"]
    assert upcoming[0]["classroom_name"] == "Матан"
    assert upcoming[0]["submitted"] is False

    everything = (
        await client.get(
            "/api/v1/assignments/upcoming", headers=student, params={"include_overdue": True}
        )
    ).json()
    assert everything[0]["title"] == "Просрочено"
    assert everything[0]["submitted"] is True


async def test_update_and_delete_assignment(
    client: AsyncClient, register: RegisterFn, auth_headers: dict[str, str]
) -> None:
    _, channel_id, student = await classroom_with_student(client, register, auth_headers)
    task = await make_assignment(client, auth_headers, channel_id)
    new_due = iso(timedelta(days=10))
    resp = await client.patch(
        f"/api/v1/assignments/{task['id']}", headers=auth_headers, json={"due_at": new_due}
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "ДЗ 1"

    assert (
        await client.delete(f"/api/v1/assignments/{task['id']}", headers=student)
    ).status_code == 403
    assert (
        await client.delete(f"/api/v1/assignments/{task['id']}", headers=auth_headers)
    ).status_code == 204
    listing = (
        await client.get(f"/api/v1/channels/{channel_id}/assignments", headers=student)
    ).json()
    assert listing == []
