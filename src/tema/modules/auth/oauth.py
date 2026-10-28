from dataclasses import dataclass
from typing import Any

import httpx
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App

from tema.core.config import Settings

YANDEX_AVATAR_URL = "https://avatars.yandex.net/get-yapic/{id}/islands-200"


@dataclass(frozen=True, slots=True)
class OAuthProfile:
    account_id: str
    email: str | None
    username: str
    first_name: str
    last_name: str
    avatar_url: str | None


def build_oauth(settings: Settings) -> OAuth:
    """Регистрирует только тех провайдеров, для которых заданы client_id и secret."""
    oauth = OAuth()
    if settings.github_client_id and settings.github_client_secret:
        oauth.register(
            "github",
            client_id=settings.github_client_id,
            client_secret=settings.github_client_secret.get_secret_value(),
            authorize_url="https://github.com/login/oauth/authorize",
            access_token_url="https://github.com/login/oauth/access_token",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "read:user user:email"},
        )
    if settings.yandex_client_id and settings.yandex_client_secret:
        oauth.register(
            "yandex",
            client_id=settings.yandex_client_id,
            client_secret=settings.yandex_client_secret.get_secret_value(),
            authorize_url="https://oauth.yandex.ru/authorize",
            access_token_url="https://oauth.yandex.ru/token",
            api_base_url="https://login.yandex.ru/",
            client_kwargs={"scope": "login:info login:email login:avatar"},
        )
    return oauth


async def fetch_profile(
    provider: str, client: StarletteOAuth2App, token: dict[str, Any]
) -> OAuthProfile:
    if provider == "github":
        user = (await client.get("user", token=token)).json()
        emails = (await client.get("user/emails", token=token)).json()
        email = next((e["email"] for e in emails if e.get("primary") and e.get("verified")), None)
        first, _, last = (user.get("name") or user["login"]).partition(" ")
        return OAuthProfile(
            account_id=str(user["id"]),
            email=email,
            username=user["login"],
            first_name=first,
            last_name=last,
            avatar_url=user.get("avatar_url"),
        )

    if provider == "yandex":
        # Яндекс ожидает заголовок "OAuth <token>", а не стандартный Bearer.
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(
                "https://login.yandex.ru/info",
                params={"format": "json"},
                headers={"Authorization": f"OAuth {token['access_token']}"},
            )
            resp.raise_for_status()
            user = resp.json()
        avatar_id = user.get("default_avatar_id")
        return OAuthProfile(
            account_id=str(user["id"]),
            email=user.get("default_email"),
            username=user["login"],
            first_name=user.get("first_name") or user["login"],
            last_name=user.get("last_name") or "",
            avatar_url=YANDEX_AVATAR_URL.format(id=avatar_id) if avatar_id else None,
        )

    raise ValueError(f"Unknown provider {provider}")
