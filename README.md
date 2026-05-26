# 员工个人记忆 AI 对话系统

公司内网部署的首版 AI 个人记忆服务，只包含员工个人持久记忆，不包含公司共享知识库。

## 功能

- 业务系统通过 HTTP POST 传入 `ldapId`、用户问题和 AI 回复，服务自动抽取个人记忆。
- 业务系统通过 HTTP GET 按 `ldapId` 读取个人记忆。
- 员工不需要账号密码。
- 记忆分为三层：个人基本信息、长期记忆、临时记忆。
- 管理员用账号密码登录后，可查看、编辑、停用和删除指定员工记忆。
- 默认使用阿里 DashScope OpenAI 兼容接口，记忆抽取模型为 `qwen-max`。
- 管理员可在前端调整当前运行时模型名称。

## 核心接口

抽取记忆：

```http
POST /api/dialogue-memories
Content-Type: application/json

{
  "ldapId": "alice001",
  "question": "记住，我喜欢中文简洁摘要。",
  "aiReply": "好的，我会记住你的回答偏好。"
}
```

读取记忆：

```http
GET /api/dialogue-memories/alice001
GET /api/dialogue-memories/alice001?layer=profile
GET /api/dialogue-memories/alice001?layer=long_term
GET /api/dialogue-memories/alice001?layer=temporary
```

管理员管理记忆：

```http
PATCH /api/admin/memories/{ldapId}/{memoryId}
DELETE /api/admin/memories/{ldapId}/{memoryId}
GET /api/admin/memories/{ldapId}/markdown
```

## Markdown 镜像

系统以数据库为主存储，同时会为每个员工自动生成三份 Markdown 镜像文件，便于管理员查看和归档：

```text
backend/data/memories/{ldapId}/profile.md
backend/data/memories/{ldapId}/long_term.md
backend/data/memories/{ldapId}/temporary.md
```

每次抽取、编辑、停用或删除记忆后，系统都会重写这三份文件。建议通过管理页面或管理 API 修改记忆，避免手工编辑 Markdown 后被下一次同步覆盖。

## 后端启动

```powershell
cd backend
py -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -e ".[dev]"
copy ..\\.env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

开发环境首次启动会自动建表并创建默认管理员：

- 用户名：`admin`
- 密码：`admin123`

生产环境不会自动建表，必须先执行 Alembic 迁移，并且必须修改默认管理员密码和 `JWT_SECRET`。

```powershell
cd backend
alembic upgrade head
```

## 前端启动

```powershell
cd frontend
npm install
npm run dev
```

前端默认访问 `http://localhost:8080`，后端默认访问 `http://localhost:8000`。

## 测试

```powershell
cd backend
pytest
```

## 生产说明

- `.env` 中配置 PostgreSQL、Redis、管理员密码、`JWT_SECRET` 和 OpenAI 兼容网关。
- 腾讯云 Docker Compose 部署见 `docs/DEPLOYMENT_TENCENT.md`。
- 当前向量字段用 JSON 保存，接口和服务层已经按员工隔离和语义召回封装；部署 PostgreSQL 后可迁移为 pgvector 原生列。
- 不要将 `.env` 或任何密钥提交到 Git。
