import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from pwdlib import PasswordHash

from tema.core.config import Settings
from tema.core.exceptions import AuthenticationError

# Argon2id — рекомендация OWASP для хранения паролей.
password_hasher = PasswordHash.recommended()

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    """Возвращает (совпал ли пароль, новый хеш если параметры алгоритма устарели)."""
    return password_hasher.verify_and_update(password, password_hash)


@dataclass(frozen=True, slots=True)
class TokenPayload:
    sub: uuid.UUID
    jti: str
    type: TokenType
    exp: datetime


def create_token(
    settings: Settings, user_id: uuid.UUID, token_type: TokenType
) -> tuple[str, TokenPayload]:
    ttl: timedelta = (
        settings.access_token_ttl if token_type == "access" else settings.refresh_token_ttl
    )
    now = datetime.now(UTC)
    payload = TokenPayload(sub=user_id, jti=uuid.uuid4().hex, type=token_type, exp=now + ttl)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "jti": payload.jti,
            "type": token_type,
            "iat": now,
            "exp": payload.exp,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, payload


def decode_token(settings: Settings, token: str, expected: TokenType) -> TokenPayload:
    try:
        data = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "jti", "type", "exp"]},
        )
        if data["type"] != expected:
            raise AuthenticationError("Неверный тип токена")
        return TokenPayload(
            sub=uuid.UUID(data["sub"]),
            jti=data["jti"],
            type=data["type"],
            exp=datetime.fromtimestamp(data["exp"], UTC),
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise AuthenticationError("Недействительный или просроченный токен") from exc
