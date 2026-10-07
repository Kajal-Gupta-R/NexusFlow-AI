# NexusFlow AI

NexusFlow AI is a secure multi-agent orchestration platform with persistent memory, background execution, task history, and human approval controls.

## Current status

Phases 1–9 are implemented. The React dashboard is connected to the authenticated FastAPI contracts for chat, orchestration, memory, conversations, task execution, status polling, and approval decisions.

## Features

- OpenAI-backed asynchronous chat
- Supervisor routing to research, coding, planning, and general agents
- Persistent conversations, memories, and task history
- Ownership-protected signed bearer sessions
- Redis/Celery background orchestration
- Queued, running, completed, failed, and cancelled task states
- Approval gates for higher-risk task descriptions
- Dashboard overview, workspace, agent monitor, memories, conversations, and tasks
- Safe API errors, request-size limits, readiness checks, and operational logging
- PostgreSQL/pgvector production path with SQLite development fallback

## Architecture

```text
React/Vite dashboard
        |
FastAPI API ---- PostgreSQL + pgvector
        |
     Redis ---- Celery worker
        |
 OpenAI + supervisor + specialized agents
```

## Project structure

```text
backend/app/       FastAPI routes, services, agents, persistence, Celery tasks
backend/migrations Alembic migrations
backend/tests/     API and repository tests
frontend/src/      React dashboard and API client
backend/Dockerfile Production API/worker image
frontend/Dockerfile Production static frontend image
docker-compose.yml PostgreSQL, Redis, API, worker, and frontend
```

## Environment

Copy templates and set local values:

```powershell
Set-Location "C:\Users\Admin\OneDrive\Attachments\MAIN PROJECT\NexusFlow AI"
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
```

Required backend values include:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
DATABASE_URL=postgresql+asyncpg://nexusflow:change-me-locally@127.0.0.1:5432/nexusflow
REDIS_URL=redis://127.0.0.1:6379/0
CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
AUTH_SECRET=replace-with-a-long-random-secret
AUTH_TOKEN_TTL=86400
```

Never commit `.env`, API keys, database passwords, or frontend secrets. The frontend only receives a short-lived signed session token and never receives `OPENAI_API_KEY`.

## Windows development

Install dependencies:

```powershell
Set-Location "C:\Users\Admin\OneDrive\Attachments\MAIN PROJECT\NexusFlow AI"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
Set-Location frontend
npm install
Set-Location ..
```

Start infrastructure in Terminal 1:

```powershell
docker compose up -d postgres redis
```

Run migrations from the repository root:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```

Start FastAPI in Terminal 2:

```powershell
$env:PYTHONPATH="backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Start Celery in Terminal 3. Windows uses the supported single-process pool:

```powershell
$env:PYTHONPATH="backend"
.\.venv\Scripts\celery.exe -A app.tasks.celery_app.celery_app worker --loglevel=INFO --pool=solo
```

Start the frontend in Terminal 4:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`.

## VPS deployment with Docker Compose

This deployment uses Caddy for automatic HTTPS, serves the frontend and API on one domain, and keeps PostgreSQL and Redis private to the Docker network. Point the domain's DNS `A`/`AAAA` record at the VPS and allow inbound TCP ports 80/443 (and UDP 443 for HTTP/3).

Copy `.env.example` to `.env`, then set `DOMAIN`, `OPENAI_API_KEY`, `POSTGRES_PASSWORD`, `AUTH_SECRET`, and `CORS_ORIGINS` to real values. Generate long random secrets, for example:

```powershell
py -c "import secrets; print(secrets.token_hex(32))"
```

Use a 64-character hex value for each password/secret, and set `CORS_ORIGINS` to include `https://<your-domain>`. Do not commit `.env`.

From the repository root on the VPS:

```sh
docker compose up -d --build
docker compose ps
docker compose logs -f backend worker caddy
```

The migration service runs before the API starts. Visit `https://<your-domain>` after Caddy obtains its certificate. PostgreSQL data, Redis data, and TLS certificates persist in named Docker volumes. Do not use `docker compose down -v` unless you intend to delete that data. An OpenAI API key is required for chat and orchestration.

## API overview

Unauthenticated:

- `GET /health`
- `GET /ready`
- `POST /auth/session`

Bearer-authenticated:

- `POST /chat`
- `POST /orchestrate`
- `GET|POST|DELETE /memory`
- `GET|DELETE /conversations`
- `GET /tasks/history`
- `POST /tasks/submit`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /tasks/{task_id}/cancel`
- `POST /tasks/{task_id}/retry`
- `POST /tasks/{task_id}/approve`
- `POST /tasks/{task_id}/reject`
- `GET /dashboard/summary`

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## Testing

Backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest backend -q
```

Lint:

```powershell
.\.venv\Scripts\python.exe -m ruff check backend
```

Frontend production build:

```powershell
Set-Location frontend
npm run build
Set-Location ..
```

Migration and compose checks:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
docker compose config
```

## Security and privacy

The API derives ownership from a server-issued signed bearer token; caller-selected identity headers are not trusted. All memories, conversations, and tasks are scoped to that identity. High-risk background tasks pause for owner approval. Errors returned to clients are generic, while logs exclude message contents and secrets. The current session mechanism is not a full account system with passwords, MFA, or OAuth; use an identity provider before exposing the service to multiple real users.

## Troubleshooting

- `/health` works but `/ready` returns `503`: start Redis with `docker compose up -d redis`.
- PostgreSQL connection failures during local development: use the SQLite URL from `backend/.env.example`; do not use SQLite for production.
- Celery does not consume tasks: verify Redis is running, `PYTHONPATH` is `backend`, and the worker command uses `--pool=solo` on Windows.
- Frontend cannot reach API: verify `frontend/.env.local` contains `VITE_API_BASE_URL=http://127.0.0.1:8000` and that CORS includes the frontend origin.
- Migration failures: confirm the database is reachable, then rerun the Alembic command from the repository root.

## Known limitations

- Live OpenAI responses require a valid backend API key.
- Docker and live Redis/Celery execution require Docker Desktop or equivalent services.
- Anonymous signed sessions provide ownership isolation but not user registration or account recovery.
- Approval policy currently uses conservative task-description keywords.
- External OpenAI requests cannot always be interrupted instantly during cancellation.
