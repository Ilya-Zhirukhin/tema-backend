"""Реестр всех ORM-моделей: импортируется Alembic-ом для autogenerate."""

from tema.core.db import Base
from tema.modules.classrooms.models import Channel, Classroom, Membership
from tema.modules.users.models import OAuthAccount, User

__all__ = ["Base", "Channel", "Classroom", "Membership", "OAuthAccount", "User"]
