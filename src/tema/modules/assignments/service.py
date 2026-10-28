import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tema.core.events import EventBus, classroom_topic
from tema.core.exceptions import AppError, ConflictError, NotFoundError, PermissionDeniedError
from tema.core.storage import Storage
from tema.modules.assignments.models import Assignment, Submission
from tema.modules.assignments.schemas import (
    AssignmentCreate,
    AssignmentRead,
    AssignmentUpdate,
    FileInfo,
    GradeRequest,
    SubmissionRead,
    UpcomingAssignment,
)
from tema.modules.classrooms.models import Channel, Classroom, MemberRole, Membership
from tema.modules.classrooms.service import ClassroomService
from tema.modules.users.models import User
from tema.modules.users.schemas import UserPublic


def submission_read(submission: Submission, assignment: Assignment) -> SubmissionRead:
    file = (
        FileInfo(
            name=submission.file_name or "file",
            content_type=submission.file_type or "application/octet-stream",
            size=submission.file_size or 0,
        )
        if submission.file_key
        else None
    )
    return SubmissionRead(
        id=submission.id,
        assignment_id=submission.assignment_id,
        student=UserPublic.model_validate(submission.student),
        text=submission.text,
        file=file,
        submitted_at=submission.submitted_at,
        is_late=submission.submitted_at > assignment.due_at,
        score=submission.score,
        feedback=submission.feedback,
        graded_at=submission.graded_at,
    )


class AssignmentService:
    """Задания создают и оценивают модераторы и владелец команды (преподаватели),
    сдают — все участники."""

    def __init__(self, session: AsyncSession, events: EventBus, storage: Storage) -> None:
        self.session = session
        self.events = events
        self.storage = storage
        self.classrooms = ClassroomService(session)

    # --- задания ---

    async def create(self, channel_id: uuid.UUID, user: User, data: AssignmentCreate) -> Assignment:
        channel = await self.classrooms.get_channel(channel_id, user, MemberRole.MODERATOR)
        assignment = Assignment(channel_id=channel_id, author_id=user.id, **data.model_dump())
        assignment.author = user
        self.session.add(assignment)
        await self.session.commit()
        await self.session.refresh(assignment)
        await self._emit(channel, "assignment.created", assignment)
        return assignment

    async def list_in_channel(self, channel_id: uuid.UUID, user: User) -> Sequence[Assignment]:
        await self.classrooms.get_channel(channel_id, user)
        stmt = (
            select(Assignment)
            .where(Assignment.channel_id == channel_id)
            .order_by(Assignment.due_at)
        )
        return (await self.session.scalars(stmt)).all()

    async def upcoming(self, user: User, *, include_overdue: bool) -> list[UpcomingAssignment]:
        """Дедлайны пользователя по всем его командам, ближайшие сверху."""
        submitted = (
            select(Submission.id)
            .where(Submission.assignment_id == Assignment.id, Submission.student_id == user.id)
            .exists()
        )
        stmt = (
            select(Assignment, Classroom.id, Classroom.name, submitted)
            .join(Channel, Channel.id == Assignment.channel_id)
            .join(Classroom, Classroom.id == Channel.classroom_id)
            .join(Membership, Membership.classroom_id == Classroom.id)
            .where(Membership.user_id == user.id)
            .order_by(Assignment.due_at)
        )
        if not include_overdue:
            stmt = stmt.where(Assignment.due_at >= datetime.now(UTC))
        rows = await self.session.execute(stmt)
        return [
            UpcomingAssignment(
                **AssignmentRead.model_validate(a).model_dump(),
                classroom_id=cid,
                classroom_name=cname,
                submitted=done,
            )
            for a, cid, cname, done in rows
        ]

    async def get(self, assignment_id: uuid.UUID, user: User) -> tuple[Assignment, Channel]:
        assignment = await self.session.get(Assignment, assignment_id)
        if assignment is None:
            raise NotFoundError("Задание не найдено")
        try:
            channel = await self.classrooms.get_channel(assignment.channel_id, user)
        except NotFoundError as exc:
            raise NotFoundError("Задание не найдено") from exc
        return assignment, channel

    async def update(
        self, assignment_id: uuid.UUID, user: User, data: AssignmentUpdate
    ) -> Assignment:
        assignment, channel = await self._get_as_teacher(assignment_id, user)
        for field, value in data.model_dump(exclude_unset=True).items():
            if value is not None or field == "max_score":
                setattr(assignment, field, value)
        await self.session.commit()
        await self.session.refresh(assignment)
        await self._emit(channel, "assignment.updated", assignment)
        return assignment

    async def delete(self, assignment_id: uuid.UUID, user: User) -> None:
        assignment, channel = await self._get_as_teacher(assignment_id, user)
        keys = list(
            await self.session.scalars(
                select(Submission.file_key).where(
                    Submission.assignment_id == assignment.id, Submission.file_key.is_not(None)
                )
            )
        )
        await self.session.delete(assignment)
        await self.session.commit()
        for key in keys:
            if key:
                await self.storage.delete(key)
        await self.events.publish(
            classroom_topic(channel.classroom_id),
            "assignment.deleted",
            {"id": str(assignment.id), "channel_id": str(channel.id)},
        )

    # --- сдача работ ---

    async def submit(
        self, assignment_id: uuid.UUID, user: User, text: str, upload: UploadFile | None
    ) -> tuple[Submission, Assignment]:
        assignment, _ = await self.get(assignment_id, user)
        if not text.strip() and upload is None:
            raise AppError("Нужно приложить файл или написать ответ")

        submission = await self._own_submission(assignment.id, user.id)
        if submission is not None and submission.graded_at is not None:
            raise ConflictError("Работа уже оценена, пересдать нельзя")

        stored = await self.storage.save(upload) if upload is not None else None
        old_key = submission.file_key if submission is not None else None
        if submission is None:
            submission = Submission(assignment_id=assignment.id, student_id=user.id)
            submission.student = user
            self.session.add(submission)

        submission.text = text
        submission.submitted_at = datetime.now(UTC)
        if stored is not None:
            submission.file_key = stored.key
            submission.file_name = stored.filename
            submission.file_type = stored.content_type
            submission.file_size = stored.size
        await self.session.commit()
        if stored is not None and old_key:
            await self.storage.delete(old_key)
        return submission, assignment

    async def my_submission(
        self, assignment_id: uuid.UUID, user: User
    ) -> tuple[Submission, Assignment]:
        assignment, _ = await self.get(assignment_id, user)
        submission = await self._own_submission(assignment.id, user.id)
        if submission is None:
            raise NotFoundError("Работа ещё не сдана")
        return submission, assignment

    async def list_submissions(
        self, assignment_id: uuid.UUID, user: User
    ) -> tuple[Sequence[Submission], Assignment]:
        assignment, _ = await self._get_as_teacher(assignment_id, user)
        stmt = (
            select(Submission)
            .where(Submission.assignment_id == assignment.id)
            .order_by(Submission.submitted_at)
        )
        return (await self.session.scalars(stmt)).all(), assignment

    async def grade(
        self, submission_id: uuid.UUID, user: User, data: GradeRequest
    ) -> tuple[Submission, Assignment]:
        submission, assignment = await self._get_submission(submission_id, user, teacher=True)
        if assignment.max_score is not None and data.score > assignment.max_score:
            raise AppError(f"Максимальный балл — {assignment.max_score}", field="score")
        submission.score = data.score
        submission.feedback = data.feedback
        submission.graded_at = datetime.now(UTC)
        submission.graded_by_id = user.id
        await self.session.commit()
        return submission, assignment

    async def submission_file(self, submission_id: uuid.UUID, user: User) -> tuple[Path, str, str]:
        submission, _ = await self._get_submission(submission_id, user, teacher=False)
        if not submission.file_key:
            raise NotFoundError("К работе не приложен файл")
        return (
            self.storage.path(submission.file_key),
            submission.file_name or "file",
            submission.file_type or "application/octet-stream",
        )

    # --- helpers ---

    async def _get_as_teacher(
        self, assignment_id: uuid.UUID, user: User
    ) -> tuple[Assignment, Channel]:
        assignment, channel = await self.get(assignment_id, user)
        await self.classrooms.require_member(channel.classroom_id, user, MemberRole.MODERATOR)
        return assignment, channel

    async def _own_submission(
        self, assignment_id: uuid.UUID, user_id: uuid.UUID
    ) -> Submission | None:
        return await self.session.scalar(
            select(Submission).where(
                Submission.assignment_id == assignment_id, Submission.student_id == user_id
            )
        )

    async def _get_submission(
        self, submission_id: uuid.UUID, user: User, *, teacher: bool
    ) -> tuple[Submission, Assignment]:
        """Работу видят её автор и преподаватели команды; оценивают только преподаватели."""
        submission = await self.session.get(Submission, submission_id)
        if submission is None:
            raise NotFoundError("Работа не найдена")
        try:
            assignment, channel = await self.get(submission.assignment_id, user)
        except NotFoundError as exc:
            raise NotFoundError("Работа не найдена") from exc
        if teacher or submission.student_id != user.id:
            try:
                await self.classrooms.require_member(
                    channel.classroom_id, user, MemberRole.MODERATOR
                )
            except PermissionDeniedError:
                if not teacher:
                    raise NotFoundError("Работа не найдена") from None
                raise
        return submission, assignment

    async def _emit(self, channel: Channel, event: str, assignment: Assignment) -> None:
        await self.events.publish(
            classroom_topic(channel.classroom_id), event, AssignmentRead.model_validate(assignment)
        )
