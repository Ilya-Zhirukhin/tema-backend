from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"


class AppError(Exception):
    """Базовая доменная ошибка. Отдаётся клиенту в формате RFC 9457 (problem+json)."""

    status_code: int = HTTPStatus.BAD_REQUEST
    code: str = "bad_request"
    detail: str = "Некорректный запрос"

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        self.detail = detail or self.detail
        self.extra = extra
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "not_found"
    detail = "Объект не найден"


class ConflictError(AppError):
    status_code = HTTPStatus.CONFLICT
    code = "conflict"
    detail = "Конфликт данных"


class AuthenticationError(AppError):
    status_code = HTTPStatus.UNAUTHORIZED
    code = "unauthorized"
    detail = "Требуется аутентификация"


class PermissionDeniedError(AppError):
    status_code = HTTPStatus.FORBIDDEN
    code = "forbidden"
    detail = "Недостаточно прав"


def _problem(request: Request, status: int, code: str, detail: Any, **extra: Any) -> JSONResponse:
    body = {
        "type": f"https://tema.dev/problems/{code}",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        **extra,
    }
    headers = {"WWW-Authenticate": "Bearer"} if status == HTTPStatus.UNAUTHORIZED else None
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return _problem(request, exc.status_code, exc.code, exc.detail, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return _problem(
            request,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "validation_error",
            "Ошибка валидации",
            errors=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTPStatus(exc.status_code).name.lower()
        return _problem(request, exc.status_code, code, exc.detail)
