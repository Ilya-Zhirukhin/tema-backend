import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tema.core.events import EventBus, classroom_topic
from tema.core.exceptions import NotFoundError, PermissionDeniedError
from tema.modules.classrooms.models import MemberRole
from tema.modules.classrooms.service import ClassroomService
from tema.modules.notes.models import Note
from tema.modules.notes.schemas import NoteCreate, NoteRead, NoteUpdate
from tema.modules.users.models import User


class NoteService:
    """Писать заметки может любой участник, закреплять — модератор и владелец."""

    def __init__(self, session: AsyncSession, events: EventBus) -> None:
        self.session = session
        self.events = events
        self.classrooms = ClassroomService(session)

    async def list(self, channel_id: uuid.UUID, user: User) -> Sequence[Note]:
        await self.classrooms.get_channel(channel_id, user)
        stmt = (
            select(Note)
            .where(Note.channel_id == channel_id)
            .order_by(Note.pinned.desc(), Note.id.desc())
        )
        return (await self.session.scalars(stmt)).all()

    async def create(self, channel_id: uuid.UUID, user: User, data: NoteCreate) -> Note:
        channel = await self.classrooms.get_channel(channel_id, user)
        if data.pinned:
            await self.classrooms.require_member(channel.classroom_id, user, MemberRole.MODERATOR)
        note = Note(channel_id=channel_id, author_id=user.id, **data.model_dump())
        note.author = user
        self.session.add(note)
        await self.session.commit()
        await self.session.refresh(note)
        await self._emit(channel.classroom_id, "note.created", note)
        return note

    async def get(self, note_id: uuid.UUID, user: User) -> Note:
        note = await self.session.get(Note, note_id)
        if note is None:
            raise NotFoundError("Заметка не найдена")
        try:
            await self.classrooms.get_channel(note.channel_id, user)
        except NotFoundError as exc:
            raise NotFoundError("Заметка не найдена") from exc
        return note

    async def update(self, note_id: uuid.UUID, user: User, data: NoteUpdate) -> Note:
        note = await self.get(note_id, user)
        channel = await self.classrooms.get_channel(note.channel_id, user)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        is_moderator = (
            await self.classrooms.require_member(channel.classroom_id, user)
        ).role.level >= MemberRole.MODERATOR.level
        if "pinned" in changes and not is_moderator:
            raise PermissionDeniedError("Закреплять заметки может модератор")
        if note.author_id != user.id and not is_moderator:
            raise PermissionDeniedError("Редактировать можно только свои заметки")
        for field, value in changes.items():
            setattr(note, field, value)
        await self.session.commit()
        await self.session.refresh(note)
        await self._emit(channel.classroom_id, "note.updated", note)
        return note

    async def delete(self, note_id: uuid.UUID, user: User) -> None:
        note = await self.get(note_id, user)
        channel = await self.classrooms.get_channel(note.channel_id, user)
        if note.author_id != user.id:
            await self.classrooms.require_member(channel.classroom_id, user, MemberRole.MODERATOR)
        await self.session.delete(note)
        await self.session.commit()
        await self.events.publish(
            classroom_topic(channel.classroom_id),
            "note.deleted",
            {"id": str(note.id), "channel_id": str(channel.id)},
        )

    async def _emit(self, classroom_id: uuid.UUID, event: str, note: Note) -> None:
        await self.events.publish(
            classroom_topic(classroom_id), event, NoteRead.model_validate(note)
        )
