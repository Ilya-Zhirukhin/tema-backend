import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from tema.modules.classrooms.models import MemberRole
from tema.modules.users.schemas import UserPublic

ClassroomName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]
ChannelName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Description = Annotated[str, Field(max_length=512)]


class ClassroomCreate(BaseModel):
    name: ClassroomName
    description: Description | None = None


class ClassroomUpdate(BaseModel):
    name: ClassroomName | None = None
    description: Description | None = None
    avatar_url: Annotated[str, Field(max_length=512)] | None = None


class ClassroomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    avatar_url: str | None
    created_at: datetime


class MyClassroom(ClassroomRead):
    """Команда в списке «мои команды»: с моей ролью; код виден модераторам и владельцу."""

    role: MemberRole
    invite_code: str | None


class JoinRequest(BaseModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=16)]


class InviteCode(BaseModel):
    invite_code: str


class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: UserPublic
    role: MemberRole
    joined_at: datetime


class MemberRoleUpdate(BaseModel):
    role: MemberRole


class ChannelCreate(BaseModel):
    name: ChannelName


class ChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    classroom_id: uuid.UUID
    name: str
    created_at: datetime
