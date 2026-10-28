import uuid

from fastapi import Response
from redis.asyncio import Redis

from tema.core.config import Settings
from tema.core.exceptions import AuthenticationError
from tema.core.security import create_token, decode_token
from tema.modules.auth.schemas import TokenResponse
from tema.modules.auth.sessions import RefreshSessionStore

REFRESH_COOKIE_PATH = "/api/v1/auth"


class TokenService:
    """Выдача пары токенов: access в теле ответа, refresh — в httpOnly cookie."""

    def __init__(self, settings: Settings, redis: Redis) -> None:
        self.settings = settings
        self.sessions = RefreshSessionStore(redis)

    async def issue(self, user_id: uuid.UUID, response: Response) -> TokenResponse:
        access, _ = create_token(self.settings, user_id, "access")
        refresh, refresh_payload = create_token(self.settings, user_id, "refresh")
        await self.sessions.save(refresh_payload)
        self.set_refresh_cookie(response, refresh)
        return TokenResponse(
            access_token=access,
            expires_in=int(self.settings.access_token_ttl.total_seconds()),
        )

    async def rotate(self, refresh_token: str | None) -> uuid.UUID:
        if not refresh_token:
            raise AuthenticationError("Нет refresh-токена")
        payload = decode_token(self.settings, refresh_token, "refresh")
        if not await self.sessions.consume(payload):
            raise AuthenticationError("Сессия истекла или отозвана")
        return payload.sub

    async def revoke(self, refresh_token: str | None, response: Response) -> None:
        self.clear_refresh_cookie(response)
        if not refresh_token:
            return
        try:
            payload = decode_token(self.settings, refresh_token, "refresh")
        except AuthenticationError:
            return
        await self.sessions.revoke(payload)

    def set_refresh_cookie(self, response: Response, token: str) -> None:
        response.set_cookie(
            self.settings.refresh_cookie_name,
            token,
            max_age=int(self.settings.refresh_token_ttl.total_seconds()),
            httponly=True,
            secure=self.settings.is_production,
            samesite="lax",
            path=REFRESH_COOKIE_PATH,
        )

    def clear_refresh_cookie(self, response: Response) -> None:
        response.delete_cookie(
            self.settings.refresh_cookie_name,
            path=REFRESH_COOKIE_PATH,
            httponly=True,
            secure=self.settings.is_production,
            samesite="lax",
        )
