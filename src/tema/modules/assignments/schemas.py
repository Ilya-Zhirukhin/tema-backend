import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from tema.modules.users.schemas import UserPublic

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text = Annotated[str, StringConstraints(max_length=20_000)]


class AssignmentCreate(BaseModel):
    title: Title
    description: Text = ""
    due_at: AwareDatetime = Field(description="Дедлайн с часовым поясом, ISO 8601")
    max_score: Annotated[int, Field(ge=1, le=1000)] | None = None


class AssignmentUpdate(BaseModel):
    title: Title | None = None
    description: Text | None = None
    due_at: AwareDatetime | None = None
    max_score: Annotated[int, Field(ge=1, le=1000)] | None = None


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel_id: uuid.UUID
    author: UserPublic | None
    title: str
    description: str
    due_at: datetime
    max_score: int | None
    created_at: datetime


class UpcomingAssignment(AssignmentRead):
    classroom_id: uuid.UUID
    classroom_name: str
    submitted: bool


class FileInfo(BaseModel):
    name: str
    content_type: str
    size: int


class SubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assignment_id: uuid.UUID
    student: UserPublic
    text: str
    file: FileInfo | None
    submitted_at: datetime
    is_late: bool
    score: int | None
    feedback: str | None
    graded_at: datetime | None


class GradeRequest(BaseModel):
    score: Annotated[int, Field(ge=0, le=1000)]
    feedback: Text | None = None
