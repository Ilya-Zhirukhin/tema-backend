from collections.abc import Awaitable, Callable
from http import HTTPStatus

from fastapi import Request

from tema.core.exceptions import AppError


class TooManyRequestsError(AppError):
    status_code = HTTPStatus.TOO_MANY_REQUESTS
    code = "too_many_requests"
    detail = "Слишком много запросов, попробуйте позже"


def client_ip(request: Request) -> str:
    # За прокси uvicorn с --proxy-headers уже подставляет адрес из X-Forwarded-For.
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, *, limit: int, window: int) -> Callable[[Request], Awaitable[None]]:
    """Зависимость FastAPI: не больше `limit` запросов за `window` секунд с одного IP.

    Фиксированное окно в Redis (INCR + EXPIRE): дёшево и общее для всех воркеров.
    """

    async def dependency(request: Request) -> None:
        settings = request.app.state.settings
        if not settings.rate_limit_enabled:
            return
        redis = request.app.state.redis
        key = f"ratelimit:{name}:{client_ip(request)}"
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, window, nx=True)
            pipe.ttl(key)
            count, _, ttl = await pipe.execute()
        if count > limit:
            raise TooManyRequestsError(retry_after=max(int(ttl), 1))

    return dependency
