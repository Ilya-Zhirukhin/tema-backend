import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from tema.api.deps import CurrentUser, EventsDep, SessionDep
from tema.modules.chat.schemas import (
    Conversation,
    DirectMessageCreate,
    DirectMessageRead,
    MessageCreate,
    MessageRead,
    MessageUpdate,
)
from tema.modules.chat.service import DirectMessageService, MessageService

router = APIRouter(tags=["messages"])
dm_router = APIRouter(prefix="/dm", tags=["direct messages"])

Limit = Annotated[int, Query(ge=1, le=100)]
Before = Annotated[uuid.UUID | None, Query(description="Курсор: id самого старого из полученных")]


@router.get("/channels/{channel_id}/messages")
async def list_messages(
    channel_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
    before: Before = None,
    limit: Limit = 50,
) -> list[MessageRead]:
    messages = await MessageService(session, events).list(
        channel_id, user, before=before, limit=limit
    )
    return [MessageRead.model_validate(m) for m in messages]


@router.post("/channels/{channel_id}/messages", status_code=status.HTTP_201_CREATED)
async def post_message(
    channel_id: uuid.UUID,
    data: MessageCreate,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
) -> MessageRead:
    message = await MessageService(session, events).post(channel_id, user, data)
    return MessageRead.model_validate(message)


@router.get("/messages/{message_id}/replies")
async def list_replies(
    message_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
    before: Before = None,
    limit: Limit = 50,
) -> list[MessageRead]:
    replies = await MessageService(session, events).replies(
        message_id, user, before=before, limit=limit
    )
    return [MessageRead.model_validate(m) for m in replies]


@router.patch("/messages/{message_id}")
async def edit_message(
    message_id: uuid.UUID,
    data: MessageUpdate,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
) -> MessageRead:
    message = await MessageService(session, events).edit(message_id, user, data)
    return MessageRead.model_validate(message)


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: uuid.UUID, user: CurrentUser, session: SessionDep, events: EventsDep
) -> None:
    await MessageService(session, events).delete(message_id, user)


@dm_router.get("")
async def list_conversations(
    user: CurrentUser, session: SessionDep, events: EventsDep
) -> list[Conversation]:
    return await DirectMessageService(session, events).conversations(user)


@dm_router.get("/{peer_id}")
async def dm_history(
    peer_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
    before: Before = None,
    limit: Limit = 50,
) -> list[DirectMessageRead]:
    messages = await DirectMessageService(session, events).history(
        user, peer_id, before=before, limit=limit
    )
    return [DirectMessageRead.model_validate(m) for m in messages]


@dm_router.post("/{peer_id}", status_code=status.HTTP_201_CREATED)
async def send_dm(
    peer_id: uuid.UUID,
    data: DirectMessageCreate,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
) -> DirectMessageRead:
    dm = await DirectMessageService(session, events).send(user, peer_id, data.content)
    return DirectMessageRead.model_validate(dm)


@dm_router.post("/{peer_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_dm_read(
    peer_id: uuid.UUID, user: CurrentUser, session: SessionDep, events: EventsDep
) -> None:
    await DirectMessageService(session, events).mark_read(user, peer_id)
