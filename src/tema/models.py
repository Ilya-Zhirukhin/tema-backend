"""Реестр всех ORM-моделей: импортируется Alembic-ом для autogenerate."""

from tema.core.db import Base
from tema.modules.assignments.models import Assignment, Submission
from tema.modules.chat.models import DirectMessage, Message
from tema.modules.classrooms.models import Channel, Classroom, Membership
from tema.modules.notes.models import Note
from tema.modules.users.models import OAuthAccount, User

__all__ = [
    "Assignment",
    "Base",
    "Channel",
    "Classroom",
    "DirectMessage",
    "Membership",
    "Message",
    "Note",
    "OAuthAccount",
    "Submission",
    "User",
]
