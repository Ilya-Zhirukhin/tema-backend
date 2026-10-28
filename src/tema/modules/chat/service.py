import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, and_, case, func, or_, select, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from tema.core.events import EventBus, classroom_topic, user_topic
from tema.core.exceptions import AppError, NotFoundError, PermissionDeniedError
from tema.modules.chat.models import DirectMessage, Message
from tema.modules.chat.schemas import (
    Conversation,
    DirectMessageRead,
    MessageCreate,
    MessageRead,
    MessageUpdate,
)
from tema.modules.classrooms.models import Channel, MemberRole
from tema.modules.classrooms.service import ClassroomService
from tema.modules.users.models import User
from tema.modules.users.schemas import UserPublic


class InvalidParentError(AppError):
    code = "invalid_parent"
    detail = "Отвечать можно только на сообщение верхнего уровня из этого же канала"


class MessageService:
    def __init__(self, session: AsyncSession, events: EventBus) -> None:
        self.session = session
        self.events = events
        self.classrooms = ClassroomService(session)

    async def list(
        self,
        channel_id: uuid.UUID,
        user: User,
        *,
        before: uuid.UUID | None,
        limit: int,
        parent_id: uuid.UUID | None = None,
    ) -> Sequence[Message]:
        """Лента канала (или тред), от новых к старым. Курсор — id последнего сообщения."""
        await self.classrooms.get_channel(channel_id, user)
        stmt = select(Message).where(Message.channel_id == channel_id)
        stmt = stmt.where(
            Message.parent_id.is_(None) if parent_id is None else Message.parent_id == parent_id
        )
        if before is not None:
            stmt = stmt.where(Message.id < before)
        rows = await self.session.scalars(stmt.order_by(Message.id.desc()).limit(limit))
        return rows.all()

    async def replies(
        self, message_id: uuid.UUID, user: User, *, before: uuid.UUID | None, limit: int
    ) -> Sequence[Message]:
        parent = await self._get(message_id, user)
        return await self.list(
            parent.channel_id, user, before=before, limit=limit, parent_id=parent.id
        )

    async def post(self, channel_id: uuid.UUID, user: User, data: MessageCreate) -> Message:
        channel = await self.classrooms.get_channel(channel_id, user)
        if data.parent_id is not None:
            parent = await self.session.get(Message, data.parent_id)
            if parent is None or parent.channel_id != channel_id or parent.parent_id is not None:
                raise InvalidParentError()

        message = Message(
            channel_id=channel_id, author_id=user.id, parent_id=data.parent_id, content=data.content
        )
        message.author = user
        self.session.add(message)
        await self.session.commit()
        await self._emit(channel, "message.created", message)
        return message

    async def edit(self, message_id: uuid.UUID, user: User, data: MessageUpdate) -> Message:
        message = await self._get(message_id, user)
        if message.author_id != user.id:
            raise PermissionDeniedError("Редактировать можно только свои сообщения")
        message.content = data.content
        message.edited_at = datetime.now(UTC)
        await self.session.commit()
        channel = await self.classrooms.get_channel(message.channel_id, user)
        await self._emit(channel, "message.updated", message)
        return message

    async def delete(self, message_id: uuid.UUID, user: User) -> None:
        message = await self._get(message_id, user)
        channel = await self.classrooms.get_channel(message.channel_id, user)
        if message.author_id != user.id:
            # Чужие сообщения удаляют модераторы и владелец.
            await self.classrooms.require_member(channel.classroom_id, user, MemberRole.MODERATOR)
        await self.session.delete(message)
        await self.session.commit()
        await self.events.publish(
            classroom_topic(channel.classroom_id),
            "message.deleted",
            {"id": str(message.id), "channel_id": str(channel.id)},
        )

    async def _get(self, message_id: uuid.UUID, user: User) -> Message:
        message = await self.session.get(Message, message_id)
        if message is None:
            raise NotFoundError("Сообщение не найдено")
        try:
            await self.classrooms.get_channel(message.channel_id, user)
        except NotFoundError as exc:
            raise NotFoundError("Сообщение не найдено") from exc
        return message

    async def _emit(self, channel: Channel, event: str, message: Message) -> None:
        await self.events.publish(
            classroom_topic(channel.classroom_id), event, MessageRead.model_validate(message)
        )


class DirectMessageService:
    def __init__(self, session: AsyncSession, events: EventBus) -> None:
        self.session = session
        self.events = events

    async def send(self, sender: User, recipient_id: uuid.UUID, content: str) -> DirectMessage:
        if recipient_id == sender.id:
            raise AppError("Нельзя написать самому себе")
        recipient = await self.session.get(User, recipient_id)
        if recipient is None or not recipient.is_active:
            raise NotFoundError("Пользователь не найден")

        dm = DirectMessage(sender_id=sender.id, recipient_id=recipient_id, content=content)
        self.session.add(dm)
        await self.session.commit()
        await self.session.refresh(dm)

        payload = DirectMessageRead.model_validate(dm)
        for uid in {sender.id, recipient_id}:
            await self.events.publish(user_topic(uid), "dm.created", payload)
        return dm

    async def history(
        self, user: User, peer_id: uuid.UUID, *, before: uuid.UUID | None, limit: int
    ) -> Sequence[DirectMessage]:
        stmt = select(DirectMessage).where(self._pair(user.id, peer_id))
        if before is not None:
            stmt = stmt.where(DirectMessage.id < before)
        rows = await self.session.scalars(stmt.order_by(DirectMessage.id.desc()).limit(limit))
        return rows.all()

    async def mark_read(self, user: User, peer_id: uuid.UUID) -> int:
        result = await self.session.execute(
            update(DirectMessage)
            .where(
                DirectMessage.sender_id == peer_id,
                DirectMessage.recipient_id == user.id,
                DirectMessage.read_at.is_(None),
            )
            .values(read_at=func.now())
        )
        await self.session.commit()
        count: int = result.rowcount  # type: ignore[attr-defined]
        if count:
            await self.events.publish(
                user_topic(peer_id), "dm.read", {"reader_id": str(user.id), "count": count}
            )
        return count

    async def conversations(self, user: User) -> list[Conversation]:
        peer = case(
            (DirectMessage.sender_id == user.id, DirectMessage.recipient_id),
            else_=DirectMessage.sender_id,
        ).label("peer_id")
        involved = or_(DirectMessage.sender_id == user.id, DirectMessage.recipient_id == user.id)

        # Последнее сообщение с каждым собеседником (DISTINCT ON — фишка Postgres).
        last_stmt = (
            select(DirectMessage, peer)
            .where(involved)
            .ext(distinct_on(peer))
            .order_by(peer, DirectMessage.id.desc())
        )
        last = {pid: msg for msg, pid in await self.session.execute(last_stmt)}
        if not last:
            return []

        unread_stmt = (
            select(DirectMessage.sender_id, func.count())
            .where(DirectMessage.recipient_id == user.id, DirectMessage.read_at.is_(None))
            .group_by(DirectMessage.sender_id)
        )
        unread_rows = await self.session.execute(unread_stmt)
        unread: dict[uuid.UUID, int] = dict(unread_rows.all())
        peers = {u.id: u for u in await self.session.scalars(select(User).where(User.id.in_(last)))}

        conversations = [
            Conversation(
                peer=UserPublic.model_validate(peers[pid]),
                last_message=DirectMessageRead.model_validate(msg),
                unread=unread.get(pid, 0),
            )
            for pid, msg in last.items()
            if pid in peers
        ]
        conversations.sort(key=lambda c: c.last_message.id, reverse=True)
        return conversations

    @staticmethod
    def _pair(a: uuid.UUID, b: uuid.UUID) -> ColumnElement[bool]:
        return or_(
            and_(DirectMessage.sender_id == a, DirectMessage.recipient_id == b),
            and_(DirectMessage.sender_id == b, DirectMessage.recipient_id == a),
        )
