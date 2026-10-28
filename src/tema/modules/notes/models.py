import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tema.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from tema.modules.users.models import User


class Note(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Заметка (пост) в канале: конспект, объявление, материалы. Текст — Markdown."""

    __tablename__ = "notes"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    pinned: Mapped[bool] = mapped_column(default=False)

    author: Mapped[User | None] = relationship(lazy="joined")
