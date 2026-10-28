"""Реестр всех ORM-моделей: импортируется Alembic-ом для autogenerate."""

from tema.core.db import Base
from tema.modules.chat.models import DirectMessage, Message
from tema.modules.classrooms.models import Channel, Classroom, Membership
from tema.modules.users.models import OAuthAccount, User

__all__ = [
    "Base",
    "Channel",
    "Classroom",
    "DirectMessage",
    "Membership",
    "Message",
    "OAuthAccount",
    "User",
]
