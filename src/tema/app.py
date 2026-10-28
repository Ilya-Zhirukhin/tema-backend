from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from tema import __version__
from tema.api import health
from tema.api.router import api_router
from tema.core.config import Settings, get_settings
from tema.core.db import Database
from tema.core.exceptions import register_exception_handlers
from tema.core.logging import RequestContextMiddleware, configure_logging
from tema.core.mail import create_mailer
from tema.core.redis import create_redis
from tema.core.storage import LocalStorage
from tema.core.telemetry import setup_telemetry
from tema.modules.auth.oauth import build_oauth


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    log = structlog.get_logger("tema")

    db = Database(settings)
    redis = create_redis(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("startup", env=settings.env, version=__version__)
        yield
        await redis.aclose()
        await db.dispose()
        log.info("shutdown")

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.db = db
    app.state.redis = redis
    app.state.oauth = build_oauth(settings)
    app.state.mailer = create_mailer(settings)
    app.state.storage = LocalStorage(settings.storage_dir, settings.max_upload_size)

    # Последний добавленный middleware выполняется первым.
    app.add_middleware(
        SessionMiddleware,  # нужен только для state в OAuth-редиректах
        secret_key=(settings.session_secret or settings.jwt_secret).get_secret_value(),
        session_cookie="tema_oauth",
        max_age=600,
        https_only=settings.is_production,
        same_site="lax",
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router)

    if settings.metrics_enabled:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator(excluded_handlers=["/health/.*", "/metrics"]).instrument(app).expose(
            app, include_in_schema=False
        )

    setup_telemetry(app, db.engine, settings)
    return app
