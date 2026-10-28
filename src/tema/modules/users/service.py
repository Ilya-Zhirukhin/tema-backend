import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from tema.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from tema.core.security import hash_password, verify_password
from tema.modules.users.models import OAuthAccount, Role, User
from tema.modules.users.repository import UserRepository
from tema.modules.users.schemas import PasswordChange, UserCreate, UserUpdate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserRepository(session)

    async def get(self, user_id: uuid.UUID) -> User:
        user = await self.repo.get(user_id)
        if user is None or not user.is_active:
            raise NotFoundError("Пользователь не найден")
        return user

    async def search(
        self, query: str | None, limit: int, offset: int
    ) -> tuple[Sequence[User], int]:
        return await self.repo.search(query, limit, offset)

    async def register(self, data: UserCreate) -> User:
        if await self.repo.exists(email=data.email):
            raise ConflictError("Email уже зарегистрирован", field="email")
        if await self.repo.exists(username=data.username):
            raise ConflictError("Имя пользователя занято", field="username")

        user = User(
            email=data.email.lower(),
            username=data.username,
            first_name=data.first_name,
            last_name=data.last_name,
            account_type=data.account_type,
            password_hash=hash_password(data.password),
        )
        self.repo.add(user)
        await self.session.commit()
        return user

    async def authenticate(self, login: str, password: str) -> User:
        user = await self.repo.get_by_login(login)
        if user is None or user.password_hash is None:
            # Хешируем впустую, чтобы время ответа не выдавало существование логина.
            hash_password(password)
            raise AuthenticationError("Неверный логин или пароль")

        ok, new_hash = verify_password(password, user.password_hash)
        if not ok:
            raise AuthenticationError("Неверный логин или пароль")
        if not user.is_active:
            raise AuthenticationError("Аккаунт деактивирован")
        if new_hash is not None:
            user.password_hash = new_hash
            await self.session.commit()
        return user

    async def update(self, user: User, data: UserUpdate) -> User:
        changes = data.model_dump(exclude_unset=True)
        new_username = changes.get("username")
        if (
            new_username
            and new_username.lower() != user.username.lower()
            and await self.repo.exists(username=new_username)
        ):
            raise ConflictError("Имя пользователя занято", field="username")
        for field, value in changes.items():
            if value is not None:
                setattr(user, field, value)
        await self.session.commit()
        return user

    async def change_password(self, user: User, data: PasswordChange) -> None:
        if user.password_hash is not None:
            ok, _ = (
                verify_password(data.current_password, user.password_hash)
                if data.current_password
                else (False, None)
            )
            if not ok:
                raise AuthenticationError("Текущий пароль указан неверно")
        user.password_hash = hash_password(data.new_password)
        await self.session.commit()

    async def delete(self, user: User) -> None:
        await self.repo.delete(user)
        await self.session.commit()

    async def set_role(self, actor: User, user_id: uuid.UUID, role: Role) -> User:
        if actor.id == user_id:
            raise PermissionDeniedError("Нельзя менять собственную роль")
        user = await self.get(user_id)
        user.role = role
        await self.session.commit()
        return user

    async def get_or_create_from_oauth(
        self,
        *,
        provider: str,
        account_id: str,
        email: str | None,
        username: str,
        first_name: str,
        last_name: str,
        avatar_url: str | None,
    ) -> User:
        user = await self.repo.get_by_oauth(provider, account_id)
        if user is not None:
            return user

        # Привязываем к существующему аккаунту только по подтверждённому провайдером email.
        if email:
            user = await self.repo.get_by_email(email)
        if user is None:
            user = User(
                email=(email or f"{provider}-{account_id}@users.noreply.tema").lower(),
                username=await self._free_username(username),
                first_name=first_name[:64] or username,
                last_name=last_name[:64],
                avatar_url=avatar_url,
                password_hash=None,
            )
            self.repo.add(user)
            await self.session.flush()

        self.repo.add(
            OAuthAccount(user_id=user.id, provider=provider, provider_account_id=account_id)
        )
        await self.session.commit()
        return user

    async def _free_username(self, base: str) -> str:
        candidate = base[:32]
        suffix = 1
        while await self.repo.exists(username=candidate):
            suffix += 1
            candidate = f"{base[: 32 - len(str(suffix)) - 1]}_{suffix}"
        return candidate
