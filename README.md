# Task Manager API

A FastAPI application for managing tasks, with JWT authentication, SQLAlchemy
persistence, Pydantic validation, rate limiting, background notifications and a
placeholder "AI suggestion" endpoint that later modules will connect to
embeddings / RAG.

## Features

- **Authentication:** register / login return a JWT (30 min expiry); passwords are
  stored as bcrypt hashes and never returned by any endpoint.
- **Tasks:** full CRUD, always scoped to the logged-in user. Another user's task
  returns `403`.
- **Filtering & pagination:** `GET /tasks?completed=&priority=&skip=&limit=`.
- **AI-ready endpoint:** `POST /tasks/{id}/suggest` returns a placeholder suggestion;
  this is where a real model plugs in later.
- **Background task:** every create / update / delete queues a notification that is
  written to `notification_log.txt` *after* the response has been sent.
- **One error format:** every error (400-500, validation, rate limit) is
  `{"error": true, "detail": "..."}`; validation errors add an `errors` list.
- **Docs:** interactive Swagger UI at `/docs`.

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | no | Create a user, returns a JWT (5/min) |
| POST | `/auth/login` | no | Returns a JWT (10/min) |
| GET | `/users/me` | yes | The authenticated user's profile |
| POST | `/tasks` | yes | Create a task (20/min) |
| GET | `/tasks` | yes | List your tasks, with filters and pagination (60/min) |
| GET | `/tasks/{id}` | yes | Get one of your tasks (60/min) |
| PATCH | `/tasks/{id}` | yes | Partially update a task (20/min) |
| DELETE | `/tasks/{id}` | yes | Delete a task, returns `204` (20/min) |
| POST | `/tasks/{id}/suggest` | yes | Placeholder AI suggestion (20/min) |

Status codes: `401` missing/invalid/expired token, `403` not your task (or inactive
account), `404` not found, `409` e-mail already registered, `422` invalid input,
`429` rate limit exceeded.

## Project structure

```
task-manager/
├── app/
│   ├── __init__.py
│   ├── main.py            # app, CORS, routers, global exception handlers
│   ├── config.py          # settings read from environment / .env
│   ├── database.py        # engine, session, Base, init_db()
│   ├── models/            # SQLAlchemy models (User, Task, Priority)
│   ├── schemas/           # Pydantic request / response schemas
│   ├── routers/           # auth.py, users.py, tasks.py
│   └── utils/             # security, exceptions, dependencies, notifications, rate_limit
├── tests/                 # pytest suite (isolated in-memory database)
├── .env.example           # copy to .env
├── pytest.ini
├── requirements.txt
└── README.md
```

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# open .env and set SECRET_KEY. Generate a value with:
python -c "import secrets; print(secrets.token_hex(32))"
```

`SECRET_KEY` is required (at least 32 characters). The app refuses to start without
it, with a message saying how to fix it.

## Run

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs, then:

1. `POST /auth/register` and copy the `access_token`
2. Click **Authorize** (top right) and paste the token
3. Create, list, update and delete tasks

The SQLite database (`app.db`) is created automatically next to the code, whichever
folder you start the server from.

## Test

```bash
python -m pytest -v
```

The tests need no `.env` and never touch `app.db`: `tests/conftest.py` points the
app at a throw-away in-memory database, a temporary notification log and a test
secret key, and resets the tables before every test. The suite covers
registration, login, token validation, every task endpoint (success and error
cases), per-user isolation, filters and pagination, the background task, the
consistent error format, rate limiting, CORS and the generated documentation.

## Configuration

All values come from environment variables or `.env` (see `.env.example`).

| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | *(required)* | Signs the JWTs; 32+ characters |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token lifetime |
| `BCRYPT_ROUNDS` | `12` | Password hashing cost |
| `DATABASE_URL` | `sqlite:///<project>/app.db` | Database location |
| `CORS_ORIGINS` | `localhost:8501`, `127.0.0.1:8501`, `localhost:3000` | Allowed browser origins (JSON list) |
| `NOTIFICATION_LOG_PATH` | `<project>/notification_log.txt` | Where notifications are written |
| `NOTIFICATION_DELAY_SECONDS` | `0` | Set to `2` to watch the background task run after the response |

## Design notes

- **Ownership is enforced in one place.** `get_owned_task` (in `utils/dependencies.py`)
  loads a task and raises `404` or `403`; GET, PATCH, DELETE and suggest all depend
  on it, so no endpoint can forget the check. `GET /tasks` filters by owner in its query.
- **Errors are never ad hoc.** Routers raise `NotFoundException`, `DuplicateException`,
  `ForbiddenException` or `UnauthorizedException`; one handler in `main.py` formats
  them, and further handlers give 404/405, validation, rate-limit and unexpected
  errors the same shape.
- **Passwords use the `bcrypt` library directly** (no passlib), so a password-hashing
  library update cannot silently break login. Passwords longer than 72 bytes are
  rejected with a `422`, because bcrypt cannot hash them.
- **E-mails are case-insensitive:** stored lower-cased and compared case-insensitively.
- **`/tasks` and `/tasks/` both work** without a redirect.

## Known limitations / next steps

- `/tasks/{id}/suggest` returns a placeholder; real AI arrives with the embeddings / RAG modules.
- Tables are created with `create_all`; a schema change needs a migration tool (Alembic)
  or deleting `app.db` during development.
- No refresh tokens or password reset yet; tokens simply expire and require a new login.
- Rate limits are counted in memory per process; use Redis storage if you run several workers.
