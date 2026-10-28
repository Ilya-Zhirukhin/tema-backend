import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis

from tema.core.security import TokenPayload


class RefreshSessionStore:
    """Refresh-токены живут в Redis: их можно отозвать (logout, смена пароля).

    refresh:{jti} -> user_id, user_sessions:{user_id} -> set(jti).
    Каждый refresh одноразовый: при использовании удаляется и выдаётся новый (rotation).
    """

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @staticmethod
    def _key(jti: str) -> str:
        return f"refresh:{jti}"

    @staticmethod
    def _user_key(user_id: uuid.UUID) -> str:
        return f"user_sessions:{user_id}"

    async def save(self, payload: TokenPayload) -> None:
        ttl = max(int((payload.exp - datetime.now(UTC)).total_seconds()), 1)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.set(self._key(payload.jti), str(payload.sub), ex=ttl)
            pipe.sadd(self._user_key(payload.sub), payload.jti)
            pipe.expire(self._user_key(payload.sub), ttl, gt=True)
            pipe.expire(self._user_key(payload.sub), ttl, nx=True)
            await pipe.execute()

    async def consume(self, payload: TokenPayload) -> bool:
        """Атомарно забирает refresh-сессию. False — токен уже использован или отозван."""
        owner = await self.redis.getdel(self._key(payload.jti))
        await self.redis.srem(self._user_key(payload.sub), payload.jti)
        return owner == str(payload.sub)

    async def revoke(self, payload: TokenPayload) -> None:
        await self.consume(payload)

    async def revoke_all(self, user_id: uuid.UUID) -> None:
        user_key = self._user_key(user_id)
        jtis = await self.redis.smembers(user_key)
        if jtis:
            await self.redis.delete(*(self._key(str(j)) for j in jtis))
        await self.redis.delete(user_key)
