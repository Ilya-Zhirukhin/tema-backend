"""Реестр всех ORM-моделей: импортируется Alembic-ом для autogenerate."""

from tema.core.db import Base
from tema.modules.users.models import OAuthAccount, User

__all__ = ["Base", "OAuthAccount", "User"]
