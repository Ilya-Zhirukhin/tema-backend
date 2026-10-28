import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse

from tema.api.deps import CurrentUser, EventsDep, SessionDep, StorageDep
from tema.modules.assignments.schemas import (
    AssignmentCreate,
    AssignmentRead,
    AssignmentUpdate,
    GradeRequest,
    SubmissionRead,
    UpcomingAssignment,
)
from tema.modules.assignments.service import AssignmentService, submission_read

router = APIRouter(tags=["assignments"])


@router.post("/channels/{channel_id}/assignments", status_code=status.HTTP_201_CREATED)
async def create_assignment(
    channel_id: uuid.UUID,
    data: AssignmentCreate,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
    storage: StorageDep,
) -> AssignmentRead:
    assignment = await AssignmentService(session, events, storage).create(channel_id, user, data)
    return AssignmentRead.model_validate(assignment)


@router.get("/channels/{channel_id}/assignments")
async def list_assignments(
    channel_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
    storage: StorageDep,
) -> list[AssignmentRead]:
    items = await AssignmentService(session, events, storage).list_in_channel(channel_id, user)
    return [AssignmentRead.model_validate(a) for a in items]


@router.get("/assignments/upcoming", summary="Мои дедлайны по всем командам")
async def upcoming_assignments(
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
    storage: StorageDep,
    include_overdue: Annotated[bool, Query()] = False,
) -> list[UpcomingAssignment]:
    return await AssignmentService(session, events, storage).upcoming(
        user, include_overdue=include_overdue
    )


@router.get("/assignments/{assignment_id}")
async def get_assignment(
    assignment_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
    storage: StorageDep,
) -> AssignmentRead:
    assignment, _ = await AssignmentService(session, events, storage).get(assignment_id, user)
    return AssignmentRead.model_validate(assignment)


@router.patch("/assignments/{assignment_id}")
async def update_assignment(
    assignment_id: uuid.UUID,
    data: AssignmentUpdate,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
    storage: StorageDep,
) -> AssignmentRead:
    assignment = await AssignmentService(session, events, storage).update(assignment_id, user, data)
    return AssignmentRead.model_validate(assignment)


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(
    assignment_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
    storage: StorageDep,
) -> None:
    await AssignmentService(session, events, storage).delete(assignment_id, user)


@router.put("/assignments/{assignment_id}/submission", summary="Сдать или пересдать работу")
async def submit(
    assignment_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
    storage: StorageDep,
    text: Annotated[str, Form(max_length=20_000)] = "",
    file: Annotated[UploadFile | None, File()] = None,
) -> SubmissionRead:
    submission, assignment = await AssignmentService(session, events, storage).submit(
        assignment_id, user, text, file
    )
    return submission_read(submission, assignment)


@router.get("/assignments/{assignment_id}/submission")
async def my_submission(
    assignment_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
    storage: StorageDep,
) -> SubmissionRead:
    submission, assignment = await AssignmentService(session, events, storage).my_submission(
        assignment_id, user
    )
    return submission_read(submission, assignment)


@router.get("/assignments/{assignment_id}/submissions", summary="Все работы (преподаватель)")
async def list_submissions(
    assignment_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
    storage: StorageDep,
) -> list[SubmissionRead]:
    items, assignment = await AssignmentService(session, events, storage).list_submissions(
        assignment_id, user
    )
    return [submission_read(s, assignment) for s in items]


@router.put("/submissions/{submission_id}/grade")
async def grade_submission(
    submission_id: uuid.UUID,
    data: GradeRequest,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
    storage: StorageDep,
) -> SubmissionRead:
    submission, assignment = await AssignmentService(session, events, storage).grade(
        submission_id, user, data
    )
    return submission_read(submission, assignment)


@router.get("/submissions/{submission_id}/file", response_class=FileResponse)
async def download_submission_file(
    submission_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    events: EventsDep,
    storage: StorageDep,
) -> FileResponse:
    path, name, content_type = await AssignmentService(session, events, storage).submission_file(
        submission_id, user
    )
    return FileResponse(path, media_type=content_type, filename=name)
