import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tema.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Role(enum.StrEnum):
    USER = "user"
    ADMIN = "admin"


class AccountType(enum.StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254))
    username: Mapped[str] = mapped_column(String(32))
    first_name: Mapped[str] = mapped_column(String(64))
    last_name: Mapped[str] = mapped_column(String(64))
    # None у пользователей, зарегистрированных только через OAuth.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, name="account_type", values_callable=lambda e: [m.value for m in e]),
        default=AccountType.STUDENT,
    )
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", values_callable=lambda e: [m.value for m in e]),
        default=Role.USER,
    )
    is_active: Mapped[bool] = mapped_column(default=True)

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="raise"
    )


# Уникальность без учёта регистра: Ivan и ivan — один и тот же логин.
Index("uq_users_email_lower", func.lower(User.email), unique=True)
Index("uq_users_username_lower", func.lower(User.username), unique=True)


class OAuthAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_account_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    provider_account_id: Mapped[str] = mapped_column(String(255))

    user: Mapped[User] = relationship(back_populates="oauth_accounts", lazy="raise")
