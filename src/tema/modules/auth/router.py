from typing import Annotated, Literal

import structlog
from authlib.integrations.base_client import OAuthError
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm

from tema.api.deps import RedisDep, SessionDep, SettingsDep
from tema.core.exceptions import AuthenticationError, NotFoundError
from tema.modules.auth.oauth import fetch_profile
from tema.modules.auth.schemas import LoginRequest, TokenResponse
from tema.modules.auth.service import TokenService
from tema.modules.users.schemas import UserCreate, UserRead
from tema.modules.users.service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])
log = structlog.get_logger(__name__)

Provider = Literal["github", "yandex"]


def get_token_service(settings: SettingsDep, redis: RedisDep) -> TokenService:
    return TokenService(settings, redis)


TokenServiceDep = Annotated[TokenService, Depends(get_token_service)]


def refresh_cookie(request: Request, settings: SettingsDep) -> str | None:
    return request.cookies.get(settings.refresh_cookie_name)


RefreshCookie = Annotated[str | None, Depends(refresh_cookie)]


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, session: SessionDep) -> UserRead:
    user = await UserService(session).register(data)
    return UserRead.model_validate(user)


@router.post("/login")
async def login(
    data: LoginRequest, response: Response, session: SessionDep, tokens: TokenServiceDep
) -> TokenResponse:
    user = await UserService(session).authenticate(data.login, data.password)
    return await tokens.issue(user.id, response)


@router.post("/token", summary="Login (OAuth2 form, для кнопки Authorize в Swagger)")
async def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    response: Response,
    session: SessionDep,
    tokens: TokenServiceDep,
) -> TokenResponse:
    user = await UserService(session).authenticate(form.username, form.password)
    return await tokens.issue(user.id, response)


@router.post("/refresh")
async def refresh(
    response: Response, session: SessionDep, tokens: TokenServiceDep, token: RefreshCookie
) -> TokenResponse:
    user_id = await tokens.rotate(token)
    user = await UserService(session).get(user_id)
    return await tokens.issue(user.id, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, tokens: TokenServiceDep, token: RefreshCookie) -> None:
    await tokens.revoke(token, response)


@router.get("/oauth/{provider}/login", include_in_schema=True)
async def oauth_login(provider: Provider, request: Request) -> Response:
    client = request.app.state.oauth.create_client(provider)
    if client is None:
        raise NotFoundError("Провайдер не настроен")
    redirect_uri = request.url_for("oauth_callback", provider=provider)
    response: Response = await client.authorize_redirect(request, str(redirect_uri))
    return response


@router.get("/oauth/{provider}/callback", name="oauth_callback")
async def oauth_callback(
    provider: Provider,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    tokens: TokenServiceDep,
) -> RedirectResponse:
    client = request.app.state.oauth.create_client(provider)
    if client is None:
        raise NotFoundError("Провайдер не настроен")
    try:
        token = await client.authorize_access_token(request)
        profile = await fetch_profile(provider, client, token)
    except OAuthError as exc:
        log.warning("oauth_failed", provider=provider, error=exc.error)
        raise AuthenticationError("Не удалось войти через провайдера") from exc

    user = await UserService(session).get_or_create_from_oauth(
        provider=provider,
        account_id=profile.account_id,
        email=profile.email,
        username=profile.username,
        first_name=profile.first_name,
        last_name=profile.last_name,
        avatar_url=profile.avatar_url,
    )
    # Фронтенд после редиректа вызывает /auth/refresh и получает access-токен.
    response = RedirectResponse(
        f"{str(settings.frontend_url).rstrip('/')}/auth/callback",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    await tokens.issue(user.id, response)
    return response
