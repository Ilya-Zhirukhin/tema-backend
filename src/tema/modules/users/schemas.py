import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from tema.modules.users.models import AccountType, Role

Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$"
    ),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Password = Annotated[str, Field(min_length=8, max_length=128)]


class UserCreate(BaseModel):
    email: EmailStr
    username: Username
    first_name: Name
    last_name: Name
    password: Password
    account_type: AccountType = AccountType.STUDENT


class UserUpdate(BaseModel):
    username: Username | None = None
    first_name: Name | None = None
    last_name: Name | None = None
    avatar_url: Annotated[str, Field(max_length=512)] | None = None


class PasswordChange(BaseModel):
    current_password: str | None = None
    new_password: Password


class RoleUpdate(BaseModel):
    role: Role


class UserPublic(BaseModel):
    """То, что видят другие пользователи (без email)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    first_name: str
    last_name: str
    avatar_url: str | None
    account_type: AccountType


class UserRead(UserPublic):
    """Полный профиль: владелец аккаунта и администраторы."""

    email: EmailStr
    role: Role
    is_active: bool
    has_password: bool
    created_at: datetime


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
