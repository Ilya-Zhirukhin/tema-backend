import uuid

from fastapi import APIRouter, status

from tema.api.deps import CurrentUser, EventsDep, SessionDep
from tema.modules.notes.schemas import NoteCreate, NoteRead, NoteUpdate
from tema.modules.notes.service import NoteService

router = APIRouter(tags=["notes"])


@router.get("/channels/{channel_id}/notes")
async def list_notes(
    channel_id: uuid.UUID, user: CurrentUser, session: SessionDep, events: EventsDep
) -> list[NoteRead]:
    notes = await NoteService(session, events).list(channel_id, user)
    return [NoteRead.model_validate(n) for n in notes]


@router.post("/channels/{channel_id}/notes", status_code=status.HTTP_201_CREATED)
async def create_note(
    channel_id: uuid.UUID,
    data: NoteCreate,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
) -> NoteRead:
    return NoteRead.model_validate(
        await NoteService(session, events).create(channel_id, user, data)
    )


@router.get("/notes/{note_id}")
async def get_note(
    note_id: uuid.UUID, user: CurrentUser, session: SessionDep, events: EventsDep
) -> NoteRead:
    return NoteRead.model_validate(await NoteService(session, events).get(note_id, user))


@router.patch("/notes/{note_id}")
async def update_note(
    note_id: uuid.UUID,
    data: NoteUpdate,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
) -> NoteRead:
    return NoteRead.model_validate(await NoteService(session, events).update(note_id, user, data))


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: uuid.UUID, user: CurrentUser, session: SessionDep, events: EventsDep
) -> None:
    await NoteService(session, events).delete(note_id, user)
