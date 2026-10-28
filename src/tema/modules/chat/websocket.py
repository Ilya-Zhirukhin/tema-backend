import contextlib
import json
import uuid
from typing import Any

import anyio
import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from redis.asyncio.client import PubSub
from sqlalchemy import select

from tema.core.events import classroom_topic, user_topic
from tema.core.exceptions import AuthenticationError
from tema.core.security import decode_token
from tema.modules.classrooms.models import Membership
from tema.modules.users.models import User

router = APIRouter(tags=["realtime"])
log = structlog.get_logger(__name__)


@router.websocket("/ws")
async def realtime(websocket: WebSocket, token: str = Query()) -> None:
    """Поток событий пользователя.

    Браузер не умеет ставить заголовки на WebSocket, поэтому access-токен идёт в query.
    Сервер присылает {"type": "ready"} после подписки, затем события вида
    {"type": "message.created", "data": {...}}. Клиент может слать {"type": "ping"}.
    Отправка сообщений — через REST, сокет только доставляет события.
    """
    app = websocket.app
    try:
        payload = decode_token(app.state.settings, token, "access")
    except AuthenticationError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with app.state.db.sessionmaker() as session:
        user = await session.get(User, payload.sub)
        if user is None or not user.is_active:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        classroom_ids = list(
            await session.scalars(
                select(Membership.classroom_id).where(Membership.user_id == user.id)
            )
        )

    await websocket.accept()
    pubsub = app.state.redis.pubsub()
    await pubsub.subscribe(user_topic(user.id), *(classroom_topic(c) for c in classroom_ids))
    await websocket.send_json({"type": "ready"})
    log.info("ws_connected", user_id=str(user.id), classrooms=len(classroom_ids))

    try:
        # anyio, а не asyncio.TaskGroup: корректно работает с отменой от сервера (cancel scope).
        async with anyio.create_task_group() as tg:
            tg.start_soon(_forward_events, websocket, pubsub)
            try:
                await _read_client(websocket)
            finally:
                tg.cancel_scope.cancel()
    except* WebSocketDisconnect:
        pass
    finally:
        # Соединение Redis нужно вернуть даже если обработчик отменили.
        with anyio.CancelScope(shield=True), contextlib.suppress(Exception):
            await pubsub.aclose()
        log.info("ws_disconnected", user_id=str(user.id))


async def _forward_events(websocket: WebSocket, pubsub: PubSub) -> None:
    async for raw in pubsub.listen():
        if raw["type"] != "message":
            continue
        event: dict[str, Any] = json.loads(raw["data"])
        etype = event["type"]
        # Вступил/вышел из команды или её удалили — меняем подписки на лету.
        if etype == "classroom.joined":
            await pubsub.subscribe(classroom_topic(uuid.UUID(event["data"]["classroom_id"])))
        elif etype == "classroom.left":
            await pubsub.unsubscribe(classroom_topic(uuid.UUID(event["data"]["classroom_id"])))
        elif etype == "classroom.deleted":
            await pubsub.unsubscribe(classroom_topic(uuid.UUID(event["data"]["id"])))
        await websocket.send_text(raw["data"])


async def _read_client(websocket: WebSocket) -> None:
    while True:
        message = await websocket.receive_json()
        if isinstance(message, dict) and message.get("type") == "ping":
            await websocket.send_json({"type": "pong"})
