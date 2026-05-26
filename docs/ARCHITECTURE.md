# Architecture

## Stack

- Backend: FastAPI, SQLAlchemy, PostgreSQL-compatible schema.
- Storage: PostgreSQL in production, SQLite-compatible fallback for local tests.
- Memory vector: JSON column in the current scaffold, wrapped behind service functions so production can migrate to pgvector.
- Jobs: Celery + Redis task definition is included; local chat path runs extraction inline for a working first slice.
- Frontend: Vite + React.

## Modules

- `auth`: admin login, token parsing, current-user dependency.
- `users`: admin-only LDAP employee record creation.
- `memory`: public `ldapId` dialogue ingestion, memory reads, admin memory CRUD, recall and extraction services.
- `jobs`: Celery app and memory extraction task.
- `shared`: configuration, database, models, schemas, security and LLM gateway.

## Data Rules

- `users.ldap_id` is the external employee identifier.
- `memories` carry `user_id` and `layer`.
- Public read/write APIs resolve `ldapId` to an internal user and never mix records across users.
- Admin APIs require JWT and can manage memory content for a specified `ldapId`.
- PostgreSQL/SQLite remains the source of truth; Markdown files under `backend/data/memories/{ldapId}/` are generated mirrors for admin review and archival.

## Model Gateway

The backend calls an OpenAI-compatible `/chat/completions` and `/embeddings` API when `OPENAI_API_KEY` is configured. Without a key, it uses deterministic mock responses and embeddings for local development and tests.
