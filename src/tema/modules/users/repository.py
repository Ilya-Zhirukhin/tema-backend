import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tema.modules.users.models import OAuthAccount, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.lower())
        return await self.session.scalar(stmt)

    async def get_by_login(self, login: str) -> User | None:
        """Ищет по email или username — пользователь может войти любым."""
        stmt = select(User).where(
            or_(
                func.lower(User.email) == login.lower(),
                func.lower(User.username) == login.lower(),
            )
        )
        return await self.session.scalar(stmt)

    async def exists(self, *, email: str | None = None, username: str | None = None) -> bool:
        conditions = []
        if email is not None:
            conditions.append(func.lower(User.email) == email.lower())
        if username is not None:
            conditions.append(func.lower(User.username) == username.lower())
        if not conditions:
            return False
        stmt = select(select(User.id).where(or_(*conditions)).exists())
        return bool(await self.session.scalar(stmt))

    async def search(
        self, query: str | None, limit: int, offset: int
    ) -> tuple[Sequence[User], int]:
        stmt = select(User).where(User.is_active.is_(True))
        if query:
            pattern = f"%{query.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.username).like(pattern),
                    func.lower(User.first_name + " " + User.last_name).like(pattern),
                )
            )
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self.session.scalars(stmt.order_by(User.username).limit(limit).offset(offset))
        return rows.all(), total or 0

    async def get_by_oauth(self, provider: str, account_id: str) -> User | None:
        stmt = (
            select(User)
            .join(OAuthAccount)
            .where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_account_id == account_id,
            )
        )
        return await self.session.scalar(stmt)

    def add(self, obj: User | OAuthAccount) -> None:
        self.session.add(obj)

    async def delete(self, user: User) -> None:
        await self.session.delete(user)
