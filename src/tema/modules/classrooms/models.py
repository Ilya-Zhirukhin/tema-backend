import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tema.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from tema.modules.users.models import User


class MemberRole(enum.StrEnum):
    MEMBER = "member"
    MODERATOR = "moderator"
    OWNER = "owner"

    @property
    def level(self) -> int:
        return list(MemberRole).index(self)


class Classroom(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Команда (класс): участники, каналы, задания."""

    __tablename__ = "classrooms"

    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String(512))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    invite_code: Mapped[str] = mapped_column(String(16), unique=True)

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="classroom", cascade="all, delete-orphan", passive_deletes=True, lazy="raise"
    )
    channels: Mapped[list[Channel]] = relationship(
        back_populates="classroom", cascade="all, delete-orphan", passive_deletes=True, lazy="raise"
    )


class Membership(Base):
    __tablename__ = "memberships"

    classroom_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, name="member_role", values_callable=lambda e: [m.value for m in e]),
        default=MemberRole.MEMBER,
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    classroom: Mapped[Classroom] = relationship(back_populates="memberships", lazy="raise")
    user: Mapped[User] = relationship(lazy="raise")


class Channel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("classroom_id", "name"),)

    classroom_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64))

    classroom: Mapped[Classroom] = relationship(back_populates="channels", lazy="raise")
