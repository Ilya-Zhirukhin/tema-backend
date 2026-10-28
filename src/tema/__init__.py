"""Tema — backend образовательной платформы (команды, каналы, чаты, задания)."""

__version__ = "0.1.0"


def main() -> None:
    """Точка входа `uv run tema`: запускает uvicorn с настройками из окружения."""
    import uvicorn

    from tema.core.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "tema.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=settings.env == "local",
        log_config=None,
        proxy_headers=True,
    )
