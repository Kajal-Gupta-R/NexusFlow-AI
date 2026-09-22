# NexusFlow AI database migrations

Run migrations from the repository root with:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```

The application also creates missing tables on startup for the SQLite development fallback. PostgreSQL deployments should run Alembic explicitly. Phase 7 adds task lifecycle columns in revision `002_background_tasks`.
