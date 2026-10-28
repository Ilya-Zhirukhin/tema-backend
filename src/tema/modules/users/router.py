import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from tema.api.deps import CurrentAdmin, CurrentUser, RedisDep, SessionDep
from tema.modules.auth.sessions import RefreshSessionStore
from tema.modules.users.schemas import (
    Page,
    PasswordChange,
    RoleUpdate,
    UserPublic,
    UserRead,
    UserUpdate,
)
from tema.modules.users.service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me")
async def update_me(data: UserUpdate, user: CurrentUser, session: SessionDep) -> UserRead:
    user = await UserService(session).update(user, data)
    return UserRead.model_validate(user)


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: PasswordChange, user: CurrentUser, session: SessionDep, redis: RedisDep
) -> None:
    await UserService(session).change_password(user, data)
    # Смена пароля разлогинивает все остальные устройства.
    await RefreshSessionStore(redis).revoke_all(user.id)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(user: CurrentUser, session: SessionDep, redis: RedisDep) -> None:
    user_id = user.id
    await UserService(session).delete(user)
    await RefreshSessionStore(redis).revoke_all(user_id)


@router.get("")
async def search_users(
    session: SessionDep,
    _: CurrentUser,
    q: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[UserPublic]:
    users, total = await UserService(session).search(q, limit, offset)
    return Page(
        items=[UserPublic.model_validate(u) for u in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{user_id}")
async def read_user(user_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(await UserService(session).get(user_id))


@router.put("/{user_id}/role")
async def set_role(
    user_id: uuid.UUID, data: RoleUpdate, admin: CurrentAdmin, session: SessionDep
) -> UserRead:
    user = await UserService(session).set_role(admin, user_id, data.role)
    return UserRead.model_validate(user)
