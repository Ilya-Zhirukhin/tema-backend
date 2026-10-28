import hashlib
import secrets
import uuid

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from tema.core.config import Settings
from tema.core.exceptions import AppError
from tema.core.mail import Email, Mailer
from tema.core.security import hash_password
from tema.modules.auth.sessions import RefreshSessionStore
from tema.modules.users.models import User
from tema.modules.users.repository import UserRepository


class InvalidResetTokenError(AppError):
    code = "invalid_reset_token"
    detail = "Ссылка для сброса пароля недействительна или устарела"


def _key(token: str) -> str:
    # В Redis храним только хеш: утечка дампа не даёт рабочих ссылок.
    return f"pwreset:{hashlib.sha256(token.encode()).hexdigest()}"


class PasswordResetService:
    def __init__(
        self, session: AsyncSession, redis: Redis, mailer: Mailer, settings: Settings
    ) -> None:
        self.session = session
        self.redis = redis
        self.mailer = mailer
        self.settings = settings

    async def request(self, email: str) -> None:
        """Всегда «успешно», чтобы по ответу нельзя было проверить, зарегистрирован ли email."""
        user = await UserRepository(self.session).get_by_email(email)
        if user is None or not user.is_active:
            return
        token = secrets.token_urlsafe(32)
        ttl = int(self.settings.password_reset_ttl.total_seconds())
        await self.redis.set(_key(token), str(user.id), ex=ttl)

        link = f"{str(self.settings.frontend_url).rstrip('/')}/reset-password?token={token}"
        await self.mailer.send(
            Email(
                to=user.email,
                subject="Сброс пароля в Tema",
                text=(
                    f"Здравствуйте, {user.first_name}!\n\n"
                    f"Чтобы задать новый пароль, перейдите по ссылке:\n{link}\n\n"
                    f"Ссылка действует {ttl // 60} минут. "
                    "Если вы не запрашивали сброс, просто проигнорируйте письмо."
                ),
            )
        )

    async def confirm(self, token: str, new_password: str) -> None:
        user_id = await self.redis.getdel(_key(token))
        if user_id is None:
            raise InvalidResetTokenError()
        user = await self.session.get(User, uuid.UUID(str(user_id)))
        if user is None or not user.is_active:
            raise InvalidResetTokenError()
        user.password_hash = hash_password(new_password)
        await self.session.commit()
        await RefreshSessionStore(self.redis).revoke_all(user.id)
