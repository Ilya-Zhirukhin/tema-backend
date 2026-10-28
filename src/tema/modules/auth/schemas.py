from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from tema.modules.users.schemas import Password


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=254, description="Email или username")
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Время жизни access-токена в секундах")


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=10, max_length=128)
    new_password: Password
