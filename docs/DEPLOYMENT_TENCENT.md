# Tencent Cloud Deployment

This project can be deployed either with Docker Compose or with native systemd services on a Tencent Cloud Linux CVM.
The current production database target is the company MySQL instance. The app must only create and use tables with the `memory_system_` prefix in the shared `ctp_rbac` database.

## Server Prerequisites

- Ubuntu 22.04 or another recent Linux distribution.
- Docker Engine and Docker Compose plugin installed if container deployment is used.
- Ports 80 and 443 opened in the Tencent Cloud security group.
- A domain name pointed to the CVM public IP if HTTPS will be enabled.
- Network access from `119.45.222.120` to `10.207.66.19:3311`.

## First Deployment

```bash
mkdir -p /opt/memory-system
cd /opt/memory-system

# Upload this repository into /opt/memory-system, then create production env:
cp .env.production.example .env
chmod 600 .env
```

Edit `.env` on the server and replace every `replace-with-*` value. Do not commit the production `.env`.
Use a MySQL SQLAlchemy URL for `DATABASE_URL`:

```text
DATABASE_URL=mysql+pymysql://perm_user:<mysql-password>@10.207.66.19:3311/ctp_rbac?charset=utf8mb4
```

```bash
docker compose -f docker-compose.prod.yml --env-file .env build
docker compose -f docker-compose.prod.yml --env-file .env up -d
docker compose -f docker-compose.prod.yml --env-file .env ps
curl -fsS http://127.0.0.1:8000/api/health
```

The backend container runs `alembic upgrade head` before starting Uvicorn. The migration creates or renames only `memory_system_*` tables.

If you are migrating an existing database that was previously created by SQLAlchemy `create_all`, back it up first, confirm the schema matches `20260526_0001_initial_schema.py`, then stamp it once instead of running the initial create migration:

```bash
docker compose -f docker-compose.prod.yml --env-file .env run --rm backend alembic stamp 20260526_0001
docker compose -f docker-compose.prod.yml --env-file .env up -d
```

## Native systemd Deployment

The current Tencent Cloud deployment at `119.45.222.120` uses this native layout:

```text
/opt/memory-system/backend
/opt/memory-system/frontend/dist
/opt/memory-system/deploy
/etc/systemd/system/memory-system-backend.service
/etc/nginx/conf.d/memory-system.conf
```

Runtime dependencies:

- MySQL network connectivity to `10.207.66.19:3311`
- Redis 7
- Nginx
- Python 3.12 virtual environment at `/opt/memory-system/backend/.venv`

Deployment sequence:

```bash
systemctl start redis-server
cd /opt/memory-system/backend
.venv/bin/pip install -e .
.venv/bin/alembic upgrade head
systemctl restart memory-system-backend
nginx -t
systemctl restart nginx
```

Health checks:

```bash
systemctl is-active memory-system-backend nginx redis-server
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://119.45.222.120:10012/api/health
```

The health response includes `"database":"mysql"` after the cutover.

## PostgreSQL to MySQL Cutover

Use this sequence for the current native deployment:

```bash
sudo systemctl stop memory-system-backend

cd /opt/memory-system/backend
.venv/bin/pip install -e .

# 1. Keep DATABASE_URL pointed at the old PostgreSQL database and rename existing tables.
.venv/bin/alembic upgrade head

# 2. Initialize the target MySQL prefixed tables.
DATABASE_URL='mysql+pymysql://perm_user:<mysql-password>@10.207.66.19:3311/ctp_rbac?charset=utf8mb4' \
  .venv/bin/alembic upgrade head

# 3. Copy data from old PostgreSQL prefixed tables into MySQL prefixed tables.
SOURCE_DATABASE_URL='<old-postgresql-sqlalchemy-url>' \
TARGET_DATABASE_URL='mysql+pymysql://perm_user:<mysql-password>@10.207.66.19:3311/ctp_rbac?charset=utf8mb4' \
  .venv/bin/python scripts/migrate_prefixed_tables.py

# 4. Update /opt/memory-system/backend/.env DATABASE_URL to the MySQL URL.
sudo systemctl start memory-system-backend
curl -fsS http://127.0.0.1:8000/api/health
```

Before running the cutover, back up the old PostgreSQL database. After the cutover, verify row counts for `memory_system_users`, `memory_system_memories`, and `memory_system_model_providers`, then create and read one test memory through the app.

## Nginx Reverse Proxy

If the host already runs system Nginx, install `deploy/nginx.memory-system.conf` as a site file and reload Nginx:

```bash
sudo cp deploy/nginx.memory-system.conf /etc/nginx/conf.d/memory-system.conf
sudo nginx -t
sudo systemctl reload nginx
```

For HTTPS, issue a certificate with your preferred ACME client and set `CORS_ORIGINS` to the final public origin, for example:

```text
CORS_ORIGINS=https://memory.example.com
```

## Upgrade

```bash
cd /opt/memory-system
docker compose -f docker-compose.prod.yml --env-file .env build
docker compose -f docker-compose.prod.yml --env-file .env up -d
docker compose -f docker-compose.prod.yml --env-file .env logs --tail=100 backend
```

## Rollback

Keep the previous deployment directory or Git revision available, then rebuild and restart from that revision. Back up the MySQL `memory_system_*` tables before running schema changes in production.
