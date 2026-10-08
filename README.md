# Intelligent File Deduplication & Storage Optimization System

A full-stack application that finds duplicate files by content, groups them, shows how much storage can be saved, and lets users remove redundant copies safely.

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, Celery, Redis, JWT
- **Frontend:** React + Vite + TypeScript, Material UI, Axios, React Router, Chart.js
- **Database:** MySQL 8.0
- **Packaging:** Docker & Docker Compose

## How duplicate detection works

1. A file is uploaded and streamed to disk in 1 MiB chunks (never fully loaded into memory). Size limit, extension blocklist and magic-number checks run first.
2. The API stores a `files` row with status `pending`, returns immediately, and queues a Celery task.
3. The Celery worker computes a streaming **SHA-256** of the file, stores it in `file_hashes`, and looks for other files of the same user with the same hash.
4. Matching files are placed in a `duplicate_groups` row. The earliest upload is the **original**, the rest are **duplicates**. Filename, upload time and location are ignored, only content matters.
5. Group numbers: `storage_consumed = size x copies`, `potential_savings = size x (copies - 1)`.

Duplicates are detected per user. Two different users uploading the same bytes are never linked, so no one can learn what another user stores.

## Quick start with Docker (recommended)

```bash
cp .env.example .env        # Windows PowerShell: Copy-Item .env.example .env
# edit .env and set real passwords and SECRET_KEY
docker compose up --build
```

| Service | URL |
|---|---|
| Web app | http://localhost:3000 |
| API + Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| MySQL (Workbench) | localhost:3306, user/password from `.env` |

Migrations run automatically when the backend container starts. Register an account on the login page and start uploading.

Stop with `docker compose down` (add `-v` to also delete the database and uploaded files).

## Running locally without Docker

You need Python 3.12, Node 20+, MySQL 8 and Redis.

### Backend

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate        macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # Windows: Copy-Item .env.example .env   (then edit DATABASE_URL etc.)
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Create the database first:

```sql
CREATE DATABASE dedup_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'dedup'@'%' IDENTIFIED BY 'change_me_db_password';
GRANT ALL PRIVILEGES ON dedup_db.* TO 'dedup'@'%';
```

### Celery worker (separate terminal, same virtualenv)

```bash
cd backend
celery -A app.worker.celery_app.celery_app worker --loglevel=info
```

**Windows:** Celery's default prefork pool does not work on Windows. Use the solo pool:

```powershell
celery -A app.worker.celery_app.celery_app worker --loglevel=info --pool=solo
```

Redis on Windows: run it with Docker (`docker run -p 6379:6379 redis:7-alpine`), WSL, or Memurai/the Redis MSI installer.
Use Python 3.12 for the backend. Newer interpreters (for example 3.14) may lack wheels for some dependencies.

For a quick test without Redis, set `CELERY_TASK_ALWAYS_EAGER=true` in `backend/.env`. Tasks then run inside the API process (uploads of large files will block the request, so use this for testing only).

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, /api is proxied to http://localhost:8000
```

Production build: `npm run build`.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest -v
```

The tests use SQLite and run Celery eagerly, so no MySQL or Redis is needed. They cover hashing (chunked streaming, identical content with different names), duplicate grouping (original selection, storage numbers, per-user isolation, idempotent reprocessing, group rebuild), safe deletion (protected files, history, original promotion), upload validation, and the full API (auth, upload, search/filter/sort/pagination, access control, delete flow, analytics).

## API overview

All endpoints are under `/api/v1`. Use **Authorize** in Swagger with a token from `/auth/login`.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Files | `POST /files/upload`, `GET /files`, `GET /files/{id}`, `GET /files/{id}/download`, `GET /files/{id}/delete-preview`, `DELETE /files/{id}?confirm=true`, `PATCH /files/{id}/protect`, `POST /files/{id}/reprocess` |
| Duplicates | `GET /duplicates/groups`, `GET /duplicates/groups/{id}`, `POST /duplicates/groups/{id}/cleanup`, `POST /duplicates/rescan` |
| Analytics | `GET /analytics/summary` |
| History | `GET /history/deletions`, `GET /history/audit` |
| System | `GET /health` |

`GET /files` supports: `q` (filename), `file_type`, `min_size`, `max_size` (bytes), `duplicate_status` (`any|duplicate|original|unique`), `date_from`, `date_to`, `sort_by` (`uploaded_at|name|size|type`), `sort_order`, `page`, `page_size`.

The OpenAPI schema is exported at `docs/openapi.json`. Import `postman/FileDedup.postman_collection.json` into Postman, run **Register** and **Login** (the token is saved automatically), then the other requests.

## Database tables

`users`, `files`, `file_hashes`, `duplicate_groups`, `file_metadata`, `deletion_history`, `audit_logs`. The schema lives in `backend/alembic/versions/0001_initial_schema.py` and is checked against the SQLAlchemy models (`alembic check` reports no differences).

## Safe deletion

- The UI fetches `GET /files/{id}/delete-preview` and shows the filename, the storage that will be freed and whether it is the last copy.
- The user must tick a confirmation box. The API refuses to delete unless `confirm=true`.
- Protected files cannot be deleted (API returns 403). "Delete all duplicates" skips protected copies and keeps the original.
- Every deletion is stored in `deletion_history` (name, hash, size, storage freed, reason) and in `audit_logs`.
- If the original is deleted, the next oldest copy becomes the original. A group with a single remaining file is dissolved.
- Bytes are removed from disk only after the database change is committed.

## Security notes

- JWT bearer authentication, bcrypt password hashing.
- Every file query is scoped to the logged-in user. Other users' files return 404.
- Stored filenames are random UUIDs, user filenames are sanitised and never used as paths, path traversal is blocked.
- Extension blocklist, executable signature detection, extension/content mismatch check for common formats, maximum upload size.
- Downloads are always sent as `application/octet-stream` with `nosniff`.
- All configuration comes from environment variables. Set a strong `SECRET_KEY` before deploying (the app logs a warning if the default is used).

## Configuration

See `.env.example` (Docker Compose) and `backend/.env.example` (running the backend directly). Main settings: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `UPLOAD_DIR`, `MAX_UPLOAD_SIZE_MB`, `HASH_CHUNK_SIZE`, `CORS_ORIGINS`, `BLOCKED_EXTENSIONS`, `LOG_LEVEL`.

## Troubleshooting

- **Files stay "Queued":** the Celery worker is not running or cannot reach Redis. Start it, then click the refresh icon on the file (or call `POST /files/{id}/reprocess`).
- **413 on upload:** raise `MAX_UPLOAD_SIZE_MB` (and the nginx `client_max_body_size` in `frontend/nginx.conf`).
- **Backend cannot connect to MySQL right after `docker compose up`:** the compose file waits for the MySQL healthcheck; on a slow first start give it up to a minute.
- **MySQL 8 auth errors with PyMySQL:** the `cryptography` package (included) is required for `caching_sha2_password`.

## Project layout

```
backend/
  app/
    api/            routes and dependencies
    core/           settings, security, logging, exceptions
    db/             engine/session
    models/         SQLAlchemy models
    schemas/        Pydantic schemas
    services/       hashing, validation, storage, duplicates, deletion, audit
    worker/         Celery app and tasks
  alembic/          migrations
  tests/            pytest suite
frontend/src/       pages, components, API client, auth context
postman/            Postman collection
docs/openapi.json   exported OpenAPI schema
docker-compose.yml
```
