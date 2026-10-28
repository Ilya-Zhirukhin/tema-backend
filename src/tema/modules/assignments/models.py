import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tema.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from tema.modules.users.models import User


class Assignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Домашнее задание с дедлайном, публикуется в канале команды."""

    __tablename__ = "assignments"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    max_score: Mapped[int | None] = mapped_column(Integer)

    author: Mapped[User | None] = relationship(lazy="joined")


class Submission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Сданная работа. Одна на студента: повторная сдача заменяет предыдущую до оценки."""

    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "student_id"),)

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text, default="")

    file_key: Mapped[str | None] = mapped_column(String(128))
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_type: Mapped[str | None] = mapped_column(String(128))
    file_size: Mapped[int | None] = mapped_column(Integer)

    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    score: Mapped[int | None] = mapped_column(Integer)
    feedback: Mapped[str | None] = mapped_column(Text)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    graded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    student: Mapped[User] = relationship(foreign_keys=[student_id], lazy="joined")
    assignment: Mapped[Assignment] = relationship(lazy="raise")
