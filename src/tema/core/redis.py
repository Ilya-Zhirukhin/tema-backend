from redis.asyncio import Redis

from tema.core.config import Settings


def create_redis(settings: Settings) -> Redis:
    return Redis.from_url(str(settings.redis_url), decode_responses=True)
