import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

import anyio
import structlog

from tema.core.config import Settings

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Email:
    to: str
    subject: str
    text: str


class Mailer(Protocol):
    async def send(self, email: Email) -> None: ...


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        if not settings.smtp_host:
            raise ValueError("TEMA_SMTP_HOST is required for SmtpMailer")
        self.settings = settings
        self.host = settings.smtp_host

    async def send(self, email: Email) -> None:
        # smtplib синхронный — отправляем в пуле потоков, чтобы не блокировать event loop.
        await anyio.to_thread.run_sync(self._send_sync, email)

    def _send_sync(self, email: Email) -> None:
        s = self.settings
        msg = EmailMessage()
        msg["From"] = s.smtp_from
        msg["To"] = email.to
        msg["Subject"] = email.subject
        msg.set_content(email.text)
        with smtplib.SMTP(self.host, s.smtp_port, timeout=15) as smtp:
            if s.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if s.smtp_user and s.smtp_password:
                smtp.login(s.smtp_user, s.smtp_password.get_secret_value())
            smtp.send_message(msg)


class LogMailer:
    """Для локальной разработки: письмо не отправляется, а пишется в лог."""

    async def send(self, email: Email) -> None:
        log.info("email", to=email.to, subject=email.subject, text=email.text)


@dataclass
class MemoryMailer:
    """Для тестов: складывает письма в список."""

    outbox: list[Email] = field(default_factory=list)

    async def send(self, email: Email) -> None:
        self.outbox.append(email)


def create_mailer(settings: Settings) -> Mailer:
    if settings.smtp_host:
        return SmtpMailer(settings)
    if settings.is_production:
        log.warning("smtp_not_configured")
    return LogMailer()
