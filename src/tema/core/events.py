import json
import uuid
from typing import Any

from pydantic import BaseModel
from redis.asyncio import Redis


def classroom_topic(classroom_id: uuid.UUID) -> str:
    return f"events:classroom:{classroom_id}"


def user_topic(user_id: uuid.UUID) -> str:
    return f"events:user:{user_id}"


class EventBus:
    """Публикация событий в Redis pub/sub. WebSocket-соединения любого воркера
    подписаны на нужные топики и пересылают события клиентам."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def publish(self, topic: str, event_type: str, data: BaseModel | dict[str, Any]) -> None:
        payload = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
        await self.redis.publish(topic, json.dumps({"type": event_type, "data": payload}))
