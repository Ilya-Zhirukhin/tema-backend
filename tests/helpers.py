from httpx import AsyncClient

from tests.conftest import PASSWORD, RegisterFn


async def login(client: AsyncClient, username: str) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/login", json={"login": username, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def classroom_with_student(
    client: AsyncClient, register: RegisterFn, teacher: dict[str, str], student: str = "student"
) -> tuple[str, str, dict[str, str]]:
    """Команда, где teacher — владелец, а student — участник. -> (room_id, channel_id, student)."""
    room = (await client.post("/api/v1/classrooms", headers=teacher, json={"name": "Матан"})).json()
    await register(username=student)
    student_headers = await login(client, student)
    resp = await client.post(
        "/api/v1/classrooms/join", headers=student_headers, json={"code": room["invite_code"]}
    )
    assert resp.status_code == 200, resp.text
    channels = (
        await client.get(f"/api/v1/classrooms/{room['id']}/channels", headers=teacher)
    ).json()
    return room["id"], channels[0]["id"], student_headers
