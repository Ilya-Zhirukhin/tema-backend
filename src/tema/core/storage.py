import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import anyio
from fastapi import UploadFile

from tema.core.exceptions import AppError

CHUNK_SIZE = 1024 * 1024


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"
    detail = "Файл слишком большой"


@dataclass(frozen=True, slots=True)
class StoredFile:
    key: str
    filename: str
    content_type: str
    size: int


class Storage(Protocol):
    """Хранилище файлов. Сейчас локальный диск; S3-совместимое добавляется отдельной
    реализацией этого протокола без изменений в модулях."""

    async def save(self, upload: UploadFile) -> StoredFile: ...

    def path(self, key: str) -> Path: ...

    async def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path, max_size: int) -> None:
        self.root = root
        self.max_size = max_size

    async def save(self, upload: UploadFile) -> StoredFile:
        # Ключ генерируем сами: имя от клиента не участвует в пути (никакого ../../).
        key = f"{uuid.uuid7().hex[:2]}/{uuid.uuid7().hex}"
        target = anyio.Path(self.path(key))
        await target.parent.mkdir(parents=True, exist_ok=True)

        size = 0
        try:
            async with await target.open("wb") as out:
                while chunk := await upload.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > self.max_size:
                        raise FileTooLargeError(
                            f"Максимальный размер файла — {self.max_size // 1024 // 1024} МБ"
                        )
                    await out.write(chunk)
        except BaseException:
            await target.unlink(missing_ok=True)
            raise

        return StoredFile(
            key=key,
            filename=Path(upload.filename or "file").name[:255],
            content_type=upload.content_type or "application/octet-stream",
            size=size,
        )

    def path(self, key: str) -> Path:
        return self.root / key

    async def delete(self, key: str) -> None:
        await anyio.Path(self.path(key)).unlink(missing_ok=True)
