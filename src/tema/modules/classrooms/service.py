import secrets
import uuid
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from tema.core.events import EventBus, classroom_topic, user_topic
from tema.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from tema.modules.classrooms.models import Channel, Classroom, MemberRole, Membership
from tema.modules.classrooms.repository import ClassroomRepository
from tema.modules.classrooms.schemas import ChannelRead, ClassroomCreate, ClassroomUpdate
from tema.modules.users.models import User

# Без похожих символов (0/O, 1/I/L), чтобы код было удобно диктовать.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
DEFAULT_CHANNEL = "General"


class ClassroomService:
    def __init__(self, session: AsyncSession, events: EventBus | None = None) -> None:
        self.session = session
        self.repo = ClassroomRepository(session)
        self.events = events

    async def _emit_classroom(
        self, classroom_id: uuid.UUID, event: str, data: BaseModel | dict[str, Any]
    ) -> None:
        if self.events is not None:
            await self.events.publish(classroom_topic(classroom_id), event, data)

    async def _emit_user(self, user_id: uuid.UUID, event: str, classroom_id: uuid.UUID) -> None:
        # WebSocket пользователя по этому событию подписывается/отписывается от команды.
        if self.events is not None:
            await self.events.publish(
                user_topic(user_id), event, {"classroom_id": str(classroom_id)}
            )

    # --- доступ ---

    async def require_member(
        self, classroom_id: uuid.UUID, user: User, min_role: MemberRole = MemberRole.MEMBER
    ) -> Membership:
        """Проверяет участие и роль. Чужим командам отвечаем 404, чтобы не раскрывать их id."""
        membership = await self.repo.get_membership(classroom_id, user.id)
        if membership is None:
            raise NotFoundError("Команда не найдена")
        if membership.role.level < min_role.level:
            raise PermissionDeniedError()
        return membership

    # --- команды ---

    async def create(self, user: User, data: ClassroomCreate) -> tuple[Classroom, Membership]:
        classroom = Classroom(
            name=data.name, description=data.description, invite_code=await self._new_code()
        )
        self.repo.add(classroom)
        await self.session.flush()
        membership = Membership(classroom_id=classroom.id, user_id=user.id, role=MemberRole.OWNER)
        self.repo.add(membership)
        self.repo.add(Channel(classroom_id=classroom.id, name=DEFAULT_CHANNEL))
        await self.session.commit()
        await self._emit_user(user.id, "classroom.joined", classroom.id)
        return classroom, membership

    async def list_mine(self, user: User) -> Sequence[tuple[Classroom, Membership]]:
        return await self.repo.list_for_user(user.id)

    async def get(self, classroom_id: uuid.UUID, user: User) -> tuple[Classroom, Membership]:
        membership = await self.require_member(classroom_id, user)
        return await self._get_classroom(classroom_id), membership

    async def update(
        self, classroom_id: uuid.UUID, user: User, data: ClassroomUpdate
    ) -> tuple[Classroom, Membership]:
        membership = await self.require_member(classroom_id, user, MemberRole.MODERATOR)
        classroom = await self._get_classroom(classroom_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            if value is not None or field != "name":
                setattr(classroom, field, value)
        await self.session.commit()
        return classroom, membership

    async def delete(self, classroom_id: uuid.UUID, user: User) -> None:
        await self.require_member(classroom_id, user, MemberRole.OWNER)
        await self.repo.delete(await self._get_classroom(classroom_id))
        await self.session.commit()
        await self._emit_classroom(classroom_id, "classroom.deleted", {"id": str(classroom_id)})

    async def regenerate_code(self, classroom_id: uuid.UUID, user: User) -> str:
        await self.require_member(classroom_id, user, MemberRole.MODERATOR)
        classroom = await self._get_classroom(classroom_id)
        classroom.invite_code = await self._new_code()
        await self.session.commit()
        return classroom.invite_code

    async def join(self, user: User, code: str) -> tuple[Classroom, Membership]:
        classroom = await self.repo.get_by_code(code.upper())
        if classroom is None:
            raise NotFoundError("Код приглашения недействителен")
        membership = await self.repo.get_membership(classroom.id, user.id)
        if membership is not None:
            raise ConflictError("Вы уже состоите в этой команде")
        membership = Membership(classroom_id=classroom.id, user_id=user.id)
        self.repo.add(membership)
        await self.session.commit()
        await self._emit_classroom(
            classroom.id,
            "member.joined",
            {"classroom_id": str(classroom.id), "user_id": str(user.id), "role": membership.role},
        )
        await self._emit_user(user.id, "classroom.joined", classroom.id)
        return classroom, membership

    # --- участники ---

    async def list_members(self, classroom_id: uuid.UUID, user: User) -> Sequence[Membership]:
        await self.require_member(classroom_id, user)
        return await self.repo.list_members(classroom_id)

    async def set_member_role(
        self, classroom_id: uuid.UUID, actor: User, user_id: uuid.UUID, role: MemberRole
    ) -> Membership:
        await self.require_member(classroom_id, actor, MemberRole.OWNER)
        if user_id == actor.id:
            raise PermissionDeniedError("Нельзя менять собственную роль")
        if role == MemberRole.OWNER:
            raise PermissionDeniedError("Передача владения пока не поддерживается")
        target = await self._get_member(classroom_id, user_id)
        target.role = role
        await self.session.commit()
        await self._emit_classroom(
            classroom_id,
            "member.updated",
            {"classroom_id": str(classroom_id), "user_id": str(user_id), "role": role},
        )
        return target

    async def remove_member(self, classroom_id: uuid.UUID, actor: User, user_id: uuid.UUID) -> None:
        """Выход из команды (себя) или исключение участника модератором/владельцем."""
        actor_membership = await self.require_member(classroom_id, actor)
        target = await self._get_member(classroom_id, user_id)
        if target.role == MemberRole.OWNER:
            raise PermissionDeniedError("Владелец не может покинуть команду, только удалить её")
        if user_id != actor.id and actor_membership.role.level <= target.role.level:
            raise PermissionDeniedError()
        await self.repo.delete(target)
        await self.session.commit()
        await self._emit_classroom(
            classroom_id,
            "member.left",
            {"classroom_id": str(classroom_id), "user_id": str(user_id)},
        )
        await self._emit_user(user_id, "classroom.left", classroom_id)

    # --- каналы ---

    async def list_channels(self, classroom_id: uuid.UUID, user: User) -> Sequence[Channel]:
        await self.require_member(classroom_id, user)
        return await self.repo.list_channels(classroom_id)

    async def create_channel(self, classroom_id: uuid.UUID, user: User, name: str) -> Channel:
        await self.require_member(classroom_id, user, MemberRole.MODERATOR)
        if await self.repo.channel_name_taken(classroom_id, name):
            raise ConflictError("Канал с таким названием уже есть", field="name")
        channel = Channel(classroom_id=classroom_id, name=name)
        self.repo.add(channel)
        await self.session.commit()
        await self._emit_classroom(
            classroom_id, "channel.created", ChannelRead.model_validate(channel)
        )
        return channel

    async def get_channel(
        self, channel_id: uuid.UUID, user: User, min_role: MemberRole = MemberRole.MEMBER
    ) -> Channel:
        channel = await self.repo.get_channel(channel_id)
        if channel is None:
            raise NotFoundError("Канал не найден")
        try:
            await self.require_member(channel.classroom_id, user, min_role)
        except NotFoundError as exc:
            raise NotFoundError("Канал не найден") from exc
        return channel

    async def rename_channel(self, channel_id: uuid.UUID, user: User, name: str) -> Channel:
        channel = await self.get_channel(channel_id, user, MemberRole.MODERATOR)
        if await self.repo.channel_name_taken(channel.classroom_id, name, exclude=channel.id):
            raise ConflictError("Канал с таким названием уже есть", field="name")
        channel.name = name
        await self.session.commit()
        await self._emit_classroom(
            channel.classroom_id, "channel.updated", ChannelRead.model_validate(channel)
        )
        return channel

    async def delete_channel(self, channel_id: uuid.UUID, user: User) -> None:
        channel = await self.get_channel(channel_id, user, MemberRole.MODERATOR)
        if len(await self.repo.list_channels(channel.classroom_id)) == 1:
            raise ConflictError("Нельзя удалить последний канал команды")
        await self.repo.delete(channel)
        await self.session.commit()
        await self._emit_classroom(
            channel.classroom_id,
            "channel.deleted",
            {"id": str(channel.id), "classroom_id": str(channel.classroom_id)},
        )

    # --- helpers ---

    async def _get_classroom(self, classroom_id: uuid.UUID) -> Classroom:
        classroom = await self.repo.get(classroom_id)
        if classroom is None:
            raise NotFoundError("Команда не найдена")
        return classroom

    async def _get_member(self, classroom_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
        membership = await self.repo.get_membership(classroom_id, user_id)
        if membership is None:
            raise NotFoundError("Участник не найден")
        return membership

    async def _new_code(self) -> str:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if not await self.repo.code_exists(code):
                return code
