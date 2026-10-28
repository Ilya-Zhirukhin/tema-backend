import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tema.core.db import Base, UUIDPrimaryKeyMixin
from tema.modules.users.models import User


class Message(UUIDPrimaryKeyMixin, Base):
    """Сообщение в канале. parent_id != None — ответ в треде."""

    __tablename__ = "messages"
    # UUIDv7 растёт со временем, поэтому (channel_id, id) — готовый индекс для пагинации.
    __table_args__ = (Index("ix_messages_channel_id_id", "channel_id", "id"),)

    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    # Удалённый пользователь не стирает историю переписки.
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    author: Mapped[User | None] = relationship(lazy="joined")


class DirectMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "direct_messages"
    __table_args__ = (
        Index("ix_direct_messages_pair", "sender_id", "recipient_id", "id"),
        Index("ix_direct_messages_recipient_unread", "recipient_id", "read_at"),
    )

    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
