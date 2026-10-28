import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from tema.modules.users.schemas import UserPublic

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Body = Annotated[str, StringConstraints(max_length=20_000)]


class NoteCreate(BaseModel):
    title: Title
    body: Body = ""
    pinned: bool = False


class NoteUpdate(BaseModel):
    title: Title | None = None
    body: Body | None = None
    pinned: bool | None = None


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel_id: uuid.UUID
    author: UserPublic | None
    title: str
    body: str
    pinned: bool
    created_at: datetime
    updated_at: datetime
