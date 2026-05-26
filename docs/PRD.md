# PRD: 员工个人记忆 AI 对话系统

## 目标

为公司员工提供一个内网 AI 个人记忆服务。首版由业务系统通过 HTTP 传入 `ldapId`、用户问题和 AI 回复，服务自动抽取并保存员工个人记忆。

## 用户

- 业务系统：按 `ldapId` 写入对话片段并读取员工记忆。
- 管理员：用账号密码登录，管理指定员工的个人记忆。

## 功能范围

- `POST /api/dialogue-memories` 接收 `ldapId`、用户问题、AI 回复，并抽取记忆。
- `GET /api/dialogue-memories/{ldapId}` 返回该员工记忆，可按 `layer` 过滤。
- 记忆分为 `profile`、`long_term`、`temporary` 三层。
- 员工不需要密码。
- 管理员可查看、编辑、停用和删除指定员工记忆。
- 生产部署必须使用 PostgreSQL、Redis、非默认 `JWT_SECRET`、非默认管理员密码和 Alembic 迁移。

## 不做

- 公司共享知识库。
- 文档上传、文件解析、RAG 文档问答。
- 企业 SSO。
- 复杂审计报表和运营看板。

## 验收标准

- 按 `ldapId` 写入的记忆不会出现在其他 `ldapId` 的 GET 结果中。
- 发送包含基本信息、长期偏好或临时任务的对话后，系统按层保存记忆。
- 未登录管理员不能调用管理接口。
- 管理员可修改记忆内容、层级和状态。
- 生产容器启动前会执行 `alembic upgrade head`。
- 生产环境若使用默认 `JWT_SECRET` 或未设置管理员密码，后端必须拒绝启动。
