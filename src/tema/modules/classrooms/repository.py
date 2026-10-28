import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from tema.modules.classrooms.models import Channel, Classroom, Membership


class ClassroomRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, classroom_id: uuid.UUID) -> Classroom | None:
        return await self.session.get(Classroom, classroom_id)

    async def get_by_code(self, code: str) -> Classroom | None:
        return await self.session.scalar(select(Classroom).where(Classroom.invite_code == code))

    async def code_exists(self, code: str) -> bool:
        stmt = select(select(Classroom.id).where(Classroom.invite_code == code).exists())
        return bool(await self.session.scalar(stmt))

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[tuple[Classroom, Membership]]:
        stmt = (
            select(Classroom, Membership)
            .join(Membership)
            .where(Membership.user_id == user_id)
            .order_by(Membership.joined_at)
        )
        return [(c, m) for c, m in await self.session.execute(stmt)]

    async def get_membership(
        self, classroom_id: uuid.UUID, user_id: uuid.UUID
    ) -> Membership | None:
        return await self.session.get(Membership, (classroom_id, user_id))

    async def list_members(self, classroom_id: uuid.UUID) -> Sequence[Membership]:
        stmt = (
            select(Membership)
            .options(joinedload(Membership.user))
            .where(Membership.classroom_id == classroom_id)
            .order_by(Membership.joined_at)
        )
        return (await self.session.scalars(stmt)).all()

    async def get_channel(self, channel_id: uuid.UUID) -> Channel | None:
        return await self.session.get(Channel, channel_id)

    async def channel_name_taken(
        self, classroom_id: uuid.UUID, name: str, exclude: uuid.UUID | None = None
    ) -> bool:
        stmt = select(Channel.id).where(Channel.classroom_id == classroom_id, Channel.name == name)
        if exclude is not None:
            stmt = stmt.where(Channel.id != exclude)
        return bool(await self.session.scalar(select(stmt.exists())))

    async def list_channels(self, classroom_id: uuid.UUID) -> Sequence[Channel]:
        stmt = (
            select(Channel)
            .where(Channel.classroom_id == classroom_id)
            .order_by(Channel.created_at, Channel.id)
        )
        return (await self.session.scalars(stmt)).all()

    def add(self, obj: Classroom | Membership | Channel) -> None:
        self.session.add(obj)

    async def delete(self, obj: Classroom | Membership | Channel) -> None:
        await self.session.delete(obj)
