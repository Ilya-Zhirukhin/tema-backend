"""WebSocket проверяем через синхронный TestClient: httpx не умеет WebSocket.

У TestClient свой event loop, поэтому для него создаётся отдельный экземпляр приложения
со своими пулами соединений.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tema.app import create_app
from tema.core.config import Settings
from tests.conftest import PASSWORD


@pytest.fixture
def tc(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        yield client


def signup(tc: TestClient, username: str) -> tuple[str, dict[str, str]]:
    tc.post(
        "/api/v1/auth/register",
        json={
            "email": f"{username}@example.com",
            "username": username,
            "first_name": "A",
            "last_name": "B",
            "password": PASSWORD,
        },
    )
    token = tc.post("/api/v1/auth/login", json={"login": username, "password": PASSWORD}).json()[
        "access_token"
    ]
    return token, {"Authorization": f"Bearer {token}"}


def receive_until(ws: Any, event_type: str) -> dict[str, Any]:
    for _ in range(10):
        event: dict[str, Any] = ws.receive_json()
        if event["type"] == event_type:
            return event
    raise AssertionError(f"no {event_type}")


def test_rejects_bad_token(tc: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect), tc.websocket_connect("/api/v1/ws?token=bad") as ws:
        ws.receive_json()


def test_ping_pong(tc: TestClient) -> None:
    token, _ = signup(tc, "ivan")
    with tc.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_channel_message_is_delivered_after_join(tc: TestClient) -> None:
    _, owner = signup(tc, "owner")
    student_token, student = signup(tc, "student")
    room = tc.post("/api/v1/classrooms", headers=owner, json={"name": "Матан"}).json()
    channel_id = tc.get(f"/api/v1/classrooms/{room['id']}/channels", headers=owner).json()[0]["id"]

    with tc.websocket_connect(f"/api/v1/ws?token={student_token}") as ws:
        assert ws.receive_json() == {"type": "ready"}

        # студент вступает уже после подключения — подписка должна обновиться на лету
        tc.post("/api/v1/classrooms/join", headers=student, json={"code": room["invite_code"]})
        receive_until(ws, "classroom.joined")

        tc.post(
            f"/api/v1/channels/{channel_id}/messages",
            headers=owner,
            json={"content": "Всем привет"},
        )
        event = receive_until(ws, "message.created")
        assert event["data"]["content"] == "Всем привет"
        assert event["data"]["author"]["username"] == "owner"

        tc.post(f"/api/v1/classrooms/{room['id']}/channels", headers=owner, json={"name": "ДЗ"})
        assert receive_until(ws, "channel.created")["data"]["name"] == "ДЗ"


def test_direct_message_is_delivered(tc: TestClient) -> None:
    _, alice = signup(tc, "alice")
    bob_token, bob = signup(tc, "bob")
    bob_id = tc.get("/api/v1/users/me", headers=bob).json()["id"]

    with tc.websocket_connect(f"/api/v1/ws?token={bob_token}") as ws:
        assert ws.receive_json() == {"type": "ready"}
        tc.post(f"/api/v1/dm/{bob_id}", headers=alice, json={"content": "Привет, Боб"})
        event = receive_until(ws, "dm.created")
        assert event["data"]["content"] == "Привет, Боб"
