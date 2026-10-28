import uuid

from fastapi import APIRouter, status

from tema.api.deps import CurrentUser, SessionDep
from tema.modules.classrooms.models import Classroom, MemberRole, Membership
from tema.modules.classrooms.schemas import (
    ChannelCreate,
    ChannelRead,
    ClassroomCreate,
    ClassroomUpdate,
    InviteCode,
    JoinRequest,
    MemberRead,
    MemberRoleUpdate,
    MyClassroom,
)
from tema.modules.classrooms.service import ClassroomService

router = APIRouter(prefix="/classrooms", tags=["classrooms"])
channels_router = APIRouter(prefix="/channels", tags=["channels"])


def to_my_classroom(classroom: Classroom, membership: Membership) -> MyClassroom:
    can_invite = membership.role.level >= MemberRole.MODERATOR.level
    return MyClassroom(
        id=classroom.id,
        name=classroom.name,
        description=classroom.description,
        avatar_url=classroom.avatar_url,
        created_at=classroom.created_at,
        role=membership.role,
        invite_code=classroom.invite_code if can_invite else None,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_classroom(
    data: ClassroomCreate, user: CurrentUser, session: SessionDep
) -> MyClassroom:
    return to_my_classroom(*await ClassroomService(session).create(user, data))


@router.get("")
async def list_my_classrooms(user: CurrentUser, session: SessionDep) -> list[MyClassroom]:
    return [to_my_classroom(c, m) for c, m in await ClassroomService(session).list_mine(user)]


@router.post("/join")
async def join_classroom(data: JoinRequest, user: CurrentUser, session: SessionDep) -> MyClassroom:
    return to_my_classroom(*await ClassroomService(session).join(user, data.code))


@router.get("/{classroom_id}")
async def get_classroom(
    classroom_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> MyClassroom:
    return to_my_classroom(*await ClassroomService(session).get(classroom_id, user))


@router.patch("/{classroom_id}")
async def update_classroom(
    classroom_id: uuid.UUID, data: ClassroomUpdate, user: CurrentUser, session: SessionDep
) -> MyClassroom:
    return to_my_classroom(*await ClassroomService(session).update(classroom_id, user, data))


@router.delete("/{classroom_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_classroom(classroom_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    await ClassroomService(session).delete(classroom_id, user)


@router.post("/{classroom_id}/invite-code")
async def regenerate_invite_code(
    classroom_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> InviteCode:
    code = await ClassroomService(session).regenerate_code(classroom_id, user)
    return InviteCode(invite_code=code)


@router.get("/{classroom_id}/members")
async def list_members(
    classroom_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[MemberRead]:
    members = await ClassroomService(session).list_members(classroom_id, user)
    return [MemberRead.model_validate(m) for m in members]


@router.put("/{classroom_id}/members/{user_id}/role")
async def set_member_role(
    classroom_id: uuid.UUID,
    user_id: uuid.UUID,
    data: MemberRoleUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> MemberRoleUpdate:
    membership = await ClassroomService(session).set_member_role(
        classroom_id, user, user_id, data.role
    )
    return MemberRoleUpdate(role=membership.role)


@router.delete("/{classroom_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    classroom_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Выйти из команды (свой user_id) или исключить участника."""
    await ClassroomService(session).remove_member(classroom_id, user, user_id)


@router.get("/{classroom_id}/channels")
async def list_channels(
    classroom_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[ChannelRead]:
    channels = await ClassroomService(session).list_channels(classroom_id, user)
    return [ChannelRead.model_validate(c) for c in channels]


@router.post("/{classroom_id}/channels", status_code=status.HTTP_201_CREATED)
async def create_channel(
    classroom_id: uuid.UUID, data: ChannelCreate, user: CurrentUser, session: SessionDep
) -> ChannelRead:
    channel = await ClassroomService(session).create_channel(classroom_id, user, data.name)
    return ChannelRead.model_validate(channel)


@channels_router.patch("/{channel_id}")
async def rename_channel(
    channel_id: uuid.UUID, data: ChannelCreate, user: CurrentUser, session: SessionDep
) -> ChannelRead:
    channel = await ClassroomService(session).rename_channel(channel_id, user, data.name)
    return ChannelRead.model_validate(channel)


@channels_router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(channel_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    await ClassroomService(session).delete_channel(channel_id, user)
