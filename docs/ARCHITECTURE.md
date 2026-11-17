# OrgWeave 架构（Phase 0）

> 状态：Phase 0 已落地。本文区分「已实现」与「规划中」，避免把设计当成功能。

## 1. 总体形态

Phase 0 采用 **模块化单体 + 独立 Worker**：

```text
Browser
  │  HTTP / WebSocket
  ▼
Next.js (apps/web)
  │  REST /api/v1
  ▼
FastAPI (apps/api) ──────────────┐
  │  SQLAlchemy async            │
  ▼                              ▼
PostgreSQL 16 + pgvector     Redis 7
  ▲                              ▲
  │                              │ jobs / heartbeats / alerts
  │                    ┌─────────┴──────────┐
  │                    │                    │
Temporal 1.29      Agent Worker        Watchdog Worker
  │                Skill Runner
  └── Temporal Worker (task queue: orgweave-phase0)
LiteLLM (模型网关)   MinIO (对象存储)
```

Phase 0 中 API 与 Worker 都是**真实进程**：API 通过 `/api/v1/health/ready` 探测依赖；Worker 向 Redis 写入带 TTL 的心跳；Temporal Worker 真实注册并执行 `PingWorkflow`。

## 2. 关键决策

### ADR-001：模块化单体优先

- 决策：业务后端保持在单个 FastAPI 应用中，按 `api / application / domain / infrastructure` 分层；Agent Worker、Temporal Worker、Skill Runner、Watchdog 独立部署。
- 原因：Phase 0 降低运维复杂度，同时保留 Worker 的独立伸缩与安全边界；后续可按模块拆分。
- 约束：不允许把业务逻辑全部堆在路由层；不允许 API 进程执行不可信代码。

### ADR-002：配置单一来源

- `orgweave_shared.settings.OrgWeaveSettings` 是 API 与全部 Worker 的唯一配置入口，读取环境变量与 `.env`。
- 校验数据库必须为 `postgresql+asyncpg://`、Redis 必须为 `redis://`/`rediss://`。
- 容器部署通过环境变量注入；`.env` 不进入镜像（`.dockerignore`）。

### ADR-003：健康检查分级

- **Liveness** `/health/live` 只证明进程可响应，不访问依赖。
- **Readiness** `/health/ready` 并行探测 PostgreSQL（含 pgvector）、Redis、MinIO、Temporal、LiteLLM，统一超时（默认 3 秒）。
- 任一依赖失败返回 HTTP 503，且包含逐项延迟与脱敏详情；不允许返回泛化 500。
- 探针失败不会泄漏 URL 中的凭据（见 `safe_error`）。

### ADR-004：对象存储初始化

- MinIO 社区镜像已从 Docker Hub/Quay 移除。Phase 0 使用 `cgr.dev/chainguard/minio`。
- API 在启动时幂等创建 `MINIO_BUCKET`；失败不阻止 liveness，但 readiness 会报告失败。这样避免了脆弱的 shell 初始化容器。

### ADR-005：Worker 心跳与看门狗

- 每个 Worker 使用统一运行时写入 `orgweave:worker:{name}:heartbeat` 哈希，并设置 TTL。
- Watchdog 扫描心跳，识别过期、时间戳缺失/非法，并向 Redis Pub/Sub 频道 `orgweave:watchdog:alerts` 发布结构化告警。
- Phase 0 只是一致性心跳层；Phase 7 才实现 Session/Run 级循环、预算与接管。

### ADR-006：WebSocket 边界

- `/ws/v1` 在 Phase 0 只提供 `hello`、`ping/pong`、`server.info`，不暴露任何租户或 Agent 数据。
- 帧上限 8 KiB，非法 JSON 返回结构化错误。
- **Phase 1 必须为每条连接加入身份与租户校验后才可扩展业务事件**，参见 `docs/SECURITY.md`。

### ADR-007：模型网关

- 通过 LiteLLM 统一模型访问，Agent Runtime 不直接依赖供应商 SDK。
- 默认别名指向 Ollama，以便无 API Key 环境下基础设施仍可启动；这不代表模型能力已可用。
- 真实 Key 只通过环境变量注入，不进入 Prompt、日志或数据库明文字段。

## 3. 分层与目录责任

| 目录 | 责任 |
|---|---|
| `apps/api/app/api` | 路由、依赖注入、请求/响应模型装配 |
| `apps/api/app/core` | 配置、数据库会话、日志入口 |
| `apps/api/app/infrastructure` | Redis/PostgreSQL/MinIO/Temporal/LiteLLM 健康适配、对象存储 |
| `apps/api/app/models` | SQLAlchemy 模型与 Alembic 元数据 |
| `apps/api/alembic` | 迁移环境与版本 |
| `packages/shared-python` | 跨服务配置、Redis、心跳、日志 |
| `packages/agent-sdk` | Agent 任务/工具契约（Phase 0 仅 envelope） |
| `packages/skill-sdk` | Skill Manifest 契约 |
| `workers/*` | 独立运行进程，只通过队列/事件/持久化数据协作 |
| `apps/web` | 系统控制台与未来业务 UI |

## 4. 运行时与部署

- 开发：`make infra` 启动依赖，API/Web/Worker 本机运行，便于调试。
- 完整容器：`make up`，所有服务由 Compose 编排，使用健康检查依赖顺序。
- 容器均以非 root（uid 10001）运行；API 与 Worker 镜像不挂载 Docker Socket。
- Temporal 使用官方 auto-setup 开发服务；生产环境必须改为持久化部署。

## 4.1 Phase 1 已实现

- 认证：Argon2id + JWT access/refresh；Next.js BFF 使用 httpOnly Cookie。
- 多租户：`X-Tenant-ID` 服务端校验 → 事务级 `app.tenant_id` → PostgreSQL FORCE RLS。
- 组织：租户、成员（human/ai）、部门层级、角色/权限、邀请、审计。
- 应用数据库账号与迁移账号分离，应用账号无 RLS 绕过能力。

## 5. Phase 0 之后的架构演进

| 阶段 | 架构增量 |
|---|---|
| Phase 1 | User/Tenant/Membership/Member/Department/Role；RLS；复合外键；JWT 与租户上下文 |
| Phase 2 | 群聊/消息/线程/附件/WebSocket 广播与已读状态 |
| Phase 3 | Agent Session/Run、Task Contract、模型调用、工具二次授权、记忆 |
| Phase 4 | 委派、Child Session、并行与依赖、结果回传 |
| Phase 5 | Skill Registry/Version、隔离 Skill Runner、MCP |
| Phase 6 | Goal/Task/审批/交付物 |
| Phase 7 | Watchdog 全量规则、Observe/Guide/Takeover/Kill、Snapshot、审计 |
| Phase 8 | Temporal 自动化、Cron/Webhook/Event、幂等与重试 |

## 6. 明确不做的事（Phase 0）

- 不实现认证、租户数据、RLS、业务表。
- 不执行 Skill 代码，不暴露执行端点。
- 不将 OpenCode 作为产品运行时依赖。
- 不伪造模型 Key 或假模型结果。
