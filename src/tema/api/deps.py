from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from tema.core.config import Settings
from tema.core.events import EventBus
from tema.core.exceptions import AuthenticationError, PermissionDeniedError
from tema.core.security import decode_token
from tema.core.storage import Storage
from tema.modules.users.models import Role, User


def get_settings(conn: HTTPConnection) -> Settings:
    settings: Settings = conn.app.state.settings
    return settings


async def get_session(conn: HTTPConnection) -> AsyncIterator[AsyncSession]:
    async for session in conn.app.state.db.session():
        yield session


def get_redis(conn: HTTPConnection) -> Redis:
    redis: Redis = conn.app.state.redis
    return redis


def get_events(conn: HTTPConnection) -> EventBus:
    return EventBus(conn.app.state.redis)


def get_storage(conn: HTTPConnection) -> Storage:
    storage: Storage = conn.app.state.storage
    return storage


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
EventsDep = Annotated[EventBus, Depends(get_events)]
StorageDep = Annotated[Storage, Depends(get_storage)]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    settings: SettingsDep,
    session: SessionDep,
) -> User:
    if not token:
        raise AuthenticationError()
    payload = decode_token(settings, token, "access")
    user = await session.get(User, payload.sub)
    if user is None or not user.is_active:
        raise AuthenticationError("Пользователь не найден или деактивирован")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_admin(user: CurrentUser) -> User:
    if user.role != Role.ADMIN:
        raise PermissionDeniedError()
    return user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]
