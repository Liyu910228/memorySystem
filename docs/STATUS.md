# Project Status

## Completed

- Git repository initialized.
- Backend FastAPI scaffold implemented.
- Admin JWT auth, LDAP user records, public dialogue-memory APIs, and admin memory APIs implemented.
- OpenAI-compatible model gateway with local mock fallback implemented.
- Celery memory extraction task scaffold added.
- React web interface implemented.
- Automated backend tests added and passing.
- Frontend production build verified.
- Alembic initial schema migration added and verified on a fresh database.
- Production startup guardrails added for `JWT_SECRET` and admin password.
- Docker Compose, Dockerfiles, Nginx reverse proxy sample, and Tencent Cloud deployment guide added.
- API-level end-to-end memory flow test added.
- Deployed to Tencent Cloud server `119.45.222.120` with native systemd backend, Nginx frontend/API proxy, PostgreSQL, and Redis.

## Current Defaults

- Development default admin: `admin` / `admin123`.
- Production requires `ADMIN_PASSWORD` and a non-default `JWT_SECRET`.
- Backend URL: `http://localhost:8000`.
- Frontend URL: `http://localhost:8080`.
- Tencent Cloud URL: `http://119.45.222.120:10012/`.
- Public write API: `POST /api/dialogue-memories`.
- Public read API: `GET /api/dialogue-memories/{ldapId}`.
- Default extraction model: `qwen-max`.
- Admin model setting API: `GET/PATCH /api/admin/model-config`.
- Markdown mirrors: `backend/data/memories/{ldapId}/profile.md`, `long_term.md`, `temporary.md`.
- Local model mode: mock unless `OPENAI_API_KEY` is set.

## Next Hardening Items

- Replace JSON vector storage with pgvector migration for production.
- Move memory extraction fully to Celery when Redis is deployed.
- Add audit log views and richer admin operations.
- Add Playwright end-to-end browser tests.
- Add HTTPS certificate automation for the final Tencent Cloud domain.
