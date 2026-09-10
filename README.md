# Task Manager API

A FastAPI application for managing tasks, with JWT authentication,
SQLAlchemy persistence, validation, background tasks, rate limiting, and a
placeholder AI-suggestion endpoint that sets up future integration with
embeddings/RAG.

## Features

- **Auth:** register / login with JWT, bcrypt-hashed passwords
- **Tasks:** full CRUD, scoped to the authenticated user (no cross-user access)
- **Filtering & pagination:** `GET /tasks` supports `completed`, `priority`, `skip`, `limit`
- **AI-ready endpoint:** `POST /tasks/{id}/suggest` — placeholder today, integration
  point for Module 7/8 embeddings + RAG work
- **Background tasks:** email-style notifications logged on create/update/delete
- **Rate limiting:** per-endpoint limits via slowapi
- **Consistent error format:** custom exceptions (`NotFoundException`,
  `DuplicateException`, `ForbiddenException`) + global exception handlers
- **Auto docs:** full Swagger UI at `/docs`

## Project Structure

```
task-manager/
├── app/
│   ├── main.py           # app factory, middleware, exception handlers
│   ├── database.py        # SQLAlchemy engine/session, Base
│   ├── models/             # SQLAlchemy models (User, Task)
│   ├── schemas/             # Pydantic request/response schemas
│   ├── routers/               # auth, tasks, users endpoints
│   └── utils/                   # security, exceptions, notifications, rate limiting, config
├── tests/
│   ├── conftest.py         # test client, isolated in-memory DB, fixtures
│   └── test_tasks.py       # pytest test suite
├── .env                      # SECRET_KEY (not committed in real projects)
├── requirements.txt
└── README.md
```

## Setup

1. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root with a secret key:

   ```
   SECRET_KEY=<your-random-secret-key>
   ```

## Running the App

```bash
uvicorn app.main:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

### Quick start via Swagger UI

1. `POST /auth/register` with a name, email, and password
2. Copy the `access_token` from the response
3. Click **Authorize** (top right) and paste the token
4. Create, list, update, and delete tasks — all scoped to your account

## Running Tests

```bash
python -m pytest tests/ -v
```

The test suite spins up an isolated in-memory SQLite database per test run
and covers: creating a task (success + validation error), listing tasks,
getting a task (found + not found), auth-required access, updating a task,
and deleting a task.

## Security Notes

- Passwords are hashed with bcrypt (never stored or returned in plaintext)
- JWTs expire after 30 minutes
- CORS is restricted to known local frontend origins
- Users can only read, update, or delete their own tasks — accessing another
  user's task returns 403

## Known Limitations / Next Steps

- `/tasks/{id}/suggest` currently returns a placeholder string; real AI
  integration is planned for Modules 7–8
- No password reset / email verification flow yet
- No refresh tokens — tokens simply expire after 30 minutes and require
  re-login
