# Tema API

Backend образовательной платформы Tema (команды, каналы, чаты, задания), переписанный с Flask
на современный асинхронный стек.

## Стек

| Задача | Инструмент |
| --- | --- |
| Язык, зависимости | Python 3.14, [uv](https://docs.astral.sh/uv/) (`uv.lock`) |
| Веб-фреймворк | FastAPI + Pydantic v2, uvicorn (uvloop) |
| База данных | PostgreSQL 18, SQLAlchemy 2 (async) + asyncpg, Alembic |
| Кеш, сессии, pub/sub | Redis 8 |
| Аутентификация | JWT (PyJWT): access в теле ответа, refresh в httpOnly cookie с ротацией; Argon2id (pwdlib); OAuth GitHub/Yandex (Authlib) |
| Наблюдаемость | structlog (JSON-логи, request id), OpenTelemetry, Prometheus `/metrics`, `/health/live` и `/health/ready` |
| Качество | ruff (линт + формат), mypy `--strict`, pytest на реальных Postgres/Redis, pre-commit, GitHub Actions |
| Деплой | многоэтапный Dockerfile на uv, docker compose |

## Структура

```
src/tema/
  app.py              # create_app(): middleware, роутеры, lifespan
  core/               # config, db, security, logging, telemetry, exceptions (RFC 9457)
  api/                # общие зависимости (SessionDep, CurrentUser), health, /api/v1
  modules/
    users/            # models → repository → service → router, schemas
    auth/             # регистрация, логин, refresh, logout, OAuth
    classrooms/       # команды, участники и роли, коды приглашения, каналы
    chat/             # сообщения в каналах, треды, личные сообщения, WebSocket
    notes/            # заметки (посты) в каналах
    assignments/      # задания, дедлайны, сдача работ с файлами, оценки
migrations/           # Alembic (async)
tests/
```

Модульный монолит: каждая фича — отдельный пакет в `modules/` со своими моделями, схемами,
репозиторием (доступ к БД), сервисом (бизнес-логика) и роутером (HTTP). Ошибки домена
бросаются как `AppError` и отдаются в формате `application/problem+json`.

## Быстрый старт

```bash
cp .env.example .env            # и задай TEMA_JWT_SECRET, например: openssl rand -hex 32
docker compose up --build       # Postgres, Redis, миграции и API на http://localhost:8000
```

Swagger: http://localhost:8000/docs

### Без Docker для API

```bash
uv sync                          # создаст .venv и поставит зависимости из uv.lock
docker compose up -d postgres redis
uv run alembic upgrade head
uv run tema                      # uvicorn с автоперезагрузкой
```

## Разработка

```bash
uv run pytest --cov              # нужна БД tema_test (TEMA_TEST_DATABASE_URL) и Redis
uv run ruff format . && uv run ruff check .
uv run mypy
uv run pre-commit install
uv run alembic revision --autogenerate -m "описание"   # новая миграция
```

Все настройки читаются из переменных окружения с префиксом `TEMA_` (см. `src/tema/core/config.py`
и `.env.example`). Секретов в коде нет.

## API v1

| Метод | Путь | Описание |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | регистрация |
| POST | `/api/v1/auth/login` | вход по email или username |
| POST | `/api/v1/auth/token` | вход OAuth2-формой (кнопка Authorize в Swagger) |
| POST | `/api/v1/auth/refresh` | новый access-токен по refresh-cookie (ротация) |
| POST | `/api/v1/auth/logout` | отзыв refresh-токена |
| GET | `/api/v1/auth/oauth/{github,yandex}/login` | вход через провайдера |
| GET/PATCH/DELETE | `/api/v1/users/me` | свой профиль |
| PUT | `/api/v1/users/me/password` | смена пароля (разлогинивает другие устройства) |
| GET | `/api/v1/users?q=` | поиск пользователей |
| GET | `/api/v1/users/{id}` | публичный профиль |
| PUT | `/api/v1/users/{id}/role` | смена роли (только admin) |
| POST/GET | `/api/v1/classrooms` | создать команду / мои команды |
| POST | `/api/v1/classrooms/join` | вступить по коду приглашения |
| GET/PATCH/DELETE | `/api/v1/classrooms/{id}` | команда (изменять — модератор, удалять — владелец) |
| POST | `/api/v1/classrooms/{id}/invite-code` | новый код приглашения |
| GET | `/api/v1/classrooms/{id}/members` | участники |
| PUT | `/api/v1/classrooms/{id}/members/{user_id}/role` | роль участника (владелец) |
| DELETE | `/api/v1/classrooms/{id}/members/{user_id}` | выйти / исключить |
| GET/POST | `/api/v1/classrooms/{id}/channels` | каналы команды |
| PATCH/DELETE | `/api/v1/channels/{id}` | переименовать / удалить канал |
| GET/POST | `/api/v1/channels/{id}/messages?before=&limit=` | лента канала (курсорная пагинация) / написать; `parent_id` — ответ в треде |
| GET | `/api/v1/messages/{id}/replies` | ответы в треде |
| PATCH/DELETE | `/api/v1/messages/{id}` | изменить своё / удалить (своё или модератором) |
| GET | `/api/v1/dm` | список диалогов с последним сообщением и счётчиком непрочитанных |
| GET/POST | `/api/v1/dm/{user_id}` | история / написать личное сообщение |
| POST | `/api/v1/dm/{user_id}/read` | отметить прочитанным |
| GET/POST | `/api/v1/channels/{id}/notes` | заметки канала (закреплённые сверху) / создать |
| GET/PATCH/DELETE | `/api/v1/notes/{id}` | заметка |
| GET/POST | `/api/v1/channels/{id}/assignments` | задания канала / создать (преподаватель) |
| GET | `/api/v1/assignments/upcoming` | мои дедлайны по всем командам |
| GET/PATCH/DELETE | `/api/v1/assignments/{id}` | задание |
| PUT/GET | `/api/v1/assignments/{id}/submission` | сдать (multipart: `text`, `file`) / моя работа |
| GET | `/api/v1/assignments/{id}/submissions` | все работы (преподаватель) |
| PUT | `/api/v1/submissions/{id}/grade` | оценить |
| GET | `/api/v1/submissions/{id}/file` | скачать файл работы |
| WS | `/api/v1/ws?token=<access>` | поток событий в реальном времени |

### Realtime

`/api/v1/ws` — один WebSocket на пользователя. Сообщения отправляются через REST, а сокет
только доставляет события: `message.created|updated|deleted`, `channel.*`, `member.*`,
`classroom.joined|left|deleted`, `dm.created`, `dm.read`. События публикуются в Redis pub/sub,
поэтому работают при любом числе воркеров и инстансов. Подписки на команды обновляются на
лету, когда пользователь вступает в команду или выходит из неё.

## План переноса из Flask-версии

- [x] Пользователи, регистрация, вход, OAuth GitHub/Yandex
- [x] Команды (classrooms), участники и роли (owner/moderator/member), коды приглашения
- [x] Каналы
- [x] Сообщения в каналах, ответы в тредах
- [x] Чаты в реальном времени: WebSocket + Redis pub/sub
- [x] Личные сообщения
- [x] Заметки (посты) в каналах
- [x] Задания с дедлайнами, сдача домашек с файлами, оценки
- [ ] Сброс пароля по email
