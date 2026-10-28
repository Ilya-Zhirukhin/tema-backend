import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from tema.modules.users.schemas import UserPublic

Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class MessageCreate(BaseModel):
    content: Content
    parent_id: uuid.UUID | None = None


class MessageUpdate(BaseModel):
    content: Content


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel_id: uuid.UUID
    parent_id: uuid.UUID | None
    author: UserPublic | None
    content: str
    created_at: datetime
    edited_at: datetime | None


class DirectMessageCreate(BaseModel):
    content: Content


class DirectMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sender_id: uuid.UUID
    recipient_id: uuid.UUID
    content: str
    created_at: datetime
    read_at: datetime | None


class Conversation(BaseModel):
    peer: UserPublic
    last_message: DirectMessageRead
    unread: int
