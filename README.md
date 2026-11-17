# OrgWeave

**AI Organization Operating System** — 以组织架构为基础、以 AI 员工为执行主体、以人类管理员为控制中心的多租户 AI 企业操作系统。

> **当前状态：Phase 0（项目基础设施）已完成。** 本阶段只交付可运行的基础设施，不包含认证、租户、组织、群聊、Agent Runtime 等业务功能。

## Phase 0 交付内容

- Next.js 15 + TypeScript + Tailwind CSS + shadcn/ui 系统控制台，展示实时依赖健康状态，支持深色/浅色主题。
- FastAPI + SQLAlchemy 2 (async) + Pydantic v2 API，统一前缀 `/api/v1`，WebSocket 前缀 `/ws/v1`。
- PostgreSQL 16 + pgvector、Redis 7、Temporal 1.29、LiteLLM、MinIO 的 Docker Compose 开发环境。
- 四个独立 Worker 骨架：Agent Worker、Temporal Worker、Skill Runner、Watchdog Worker，均带真实心跳。
- Alembic 基线迁移（pgvector 扩展 + `system_settings`）。
- 真实健康检查：API readiness 逐项探测 PostgreSQL、Redis、MinIO、Temporal、LiteLLM。
- pytest 单元 + 集成测试、Ruff、ESLint、TypeScript 检查、GitHub Actions CI。
- Phase 0 架构与子系统文档。

## 环境要求

| 工具 | 版本 |
|---|---|
| Docker Engine + Compose v2 | Docker 24+ / Compose 2.20+ |
| Python | 3.11+（含 `python3-venv`） |
| Node.js | 20+ |
| pnpm | 9.x |
| GNU Make | 任意现代版本 |

当前开发机特殊说明：

- 若当前 shell 未刷新 `docker` 组，使用 `sg docker -c "make up"`，或先执行 `newgrp docker`。
- 若系统缺少 `python3-venv`，先安装：`sudo apt install python3.13-venv`（或对应版本）。

## 快速开始

```bash
cp .env.example .env

# 一键：创建 venv、安装依赖、启动基础设施、执行迁移
make bootstrap

# 方式 A：本机开发进程
make api       # 终端 1，http://localhost:8000
make web       # 终端 2，http://localhost:3000
make workers   # 启动 4 个 Worker（后台，日志在 .data/logs）

# 方式 B：完整 Docker 栈
make up        # 构建并启动全部服务，包含 API/Web/Workers
make ps
```

停止本机 Worker：`make workers-stop`。停止完整栈：`make down`。

## 服务地址

| 服务 | 地址 | 说明 |
|---|---|---|
| Web 控制台 | http://localhost:3000 | Phase 0 状态面板 |
| API | http://localhost:8000 | `/api/v1` |
| API 文档 | http://localhost:8000/api/v1/docs | Swagger UI |
| OpenAPI | http://localhost:8000/api/v1/openapi.json | 契约 |
| WebSocket | ws://localhost:8000/ws/v1 | hello / ping / server.info |
| Temporal UI | http://localhost:8080 | 工作流 |
| Temporal gRPC | localhost:7233 | |
| LiteLLM | http://localhost:4000 | `/health/liveliness` |
| MinIO API / 控制台 | http://localhost:9000 / http://localhost:9001 | 凭据见 `.env` |
| Skill Runner | http://localhost:8001/health/live | 仅健康检查 |
| PostgreSQL | localhost:5432 | `orgweave` / 见 `.env` |
| Redis | localhost:6379 | |

## 验收与测试

```bash
# 全量 Phase 0 验收（需要 make up 启动完整栈）
make verify

# 仅 Python 测试
ORGWEAVE_INTEGRATION=1 make test     # 集成测试需要基础设施
make test-unit                        # 跳过集成测试

# 前端检查
pnpm lint
pnpm typecheck
pnpm --filter @orgweave/web build

# Temporal 端到端烟雾测试（Temporal Worker 需运行）
make temporal-test
```

本机实测（2026-11-17，完整 Docker Compose 栈）：

- `docker compose config -q` 通过，全部 12 个服务启动；依赖容器均 `healthy`。
- PostgreSQL 16.16 + pgvector 0.8.7、Redis、Temporal 1.29.7、LiteLLM、MinIO 均健康。
- `alembic upgrade head` / `downgrade base` / `upgrade head` 通过。
- `pytest`：**44 passed**（含真实基础设施集成测试）。
- Web：ESLint 0 错误、TypeScript 通过、`next build` 通过、页面返回 200 且渲染真实 `ready` 状态。
- 容器内 4 个 Worker 心跳均出现在 Redis；Agent Worker 真实消费 `system.ping` 并返回结果。
- Temporal `PingWorkflow` 端到端成功。
- `make verify`：**20 passed, 0 failed**。

## 目录结构

```text
apps/
  api/                 FastAPI、Alembic、pytest
  web/                 Next.js 15 控制台
workers/
  agent-worker/        Redis 队列消费 + 心跳 + 死信
  temporal-worker/     Temporal Worker + PingWorkflow
  skill-runner/        健康检查服务 + 心跳（无执行端点）
  watchdog-worker/     Worker 心跳过期检测 + Redis 告警
packages/
  shared-python/       配置、Redis、日志、心跳、关闭处理
  agent-sdk/           AgentJob / JobResult / ToolSpec 契约
  skill-sdk/           SkillManifest 契约
  shared-types/        TypeScript API 类型
infra/
  docker/              应用与 Worker Dockerfile
  postgres/init/       pgvector / pgcrypto 初始化
  temporal/            动态配置
  litellm/             LiteLLM 配置
docs/                  架构与子系统文档
scripts/                bootstrap / health / verify / worker / temporal smoke
```

## 关键配置

所有配置集中在根目录 `.env`，由 `packages/shared-python/src/orgweave_shared/settings.py` 读取。`.env.example` 不含真实密钥。

- `LITELLM_MASTER_KEY` 是开发占位值，生产环境必须替换。
- LiteLLM 默认别名 `orgweave-default` 指向本机 Ollama（`OLLAMA_BASE_URL`），因此**没有任何模型 API Key 时整套基础设施仍可启动**。真实模型调用需运行 Ollama 或自行添加供应商模型。
- MinIO 社区镜像已从 Docker Hub 移除，本项目使用 Chainguard 维护的 `cgr.dev/chainguard/minio`。对象桶由 API 启动时幂等创建。
- 生产环境不得使用 Temporal 开发模式；Phase 0 仅用于本地开发。

## 已知限制（Phase 0 范围内）

- 没有登录、用户、租户、成员或权限系统；计划 Phase 1。
- `/ws/v1` 仅提供无业务数据的握手与 ping/pong；认证与业务事件在 Phase 1/2 加入。
- Agent Worker 只处理 `system.ping`，其余任务进入死信队列；真实 Agent Runtime 在 Phase 3。
- Skill Runner **不执行任何代码**，避免在隔离机制完成前暴露执行面；执行能力在 Phase 5。
- Watchdog 只检测 Worker 心跳过期；Session/Run 循环与预算监控在 Phase 7。
- 未配置 Prometheus/Grafana；监控接入在后续阶段规划。

## 文档

- [架构](docs/ARCHITECTURE.md)
- [数据库](docs/DATABASE.md)
- [API](docs/API.md)
- [安全](docs/SECURITY.md)
- [Agent Runtime](docs/AGENT_RUNTIME.md)
- [人工接管](docs/TAKEOVER.md)
- [路线图](docs/ROADMAP.md)
- [实现总指令](docs/IMPLEMENTATION_MASTER_PROMPT.md)

## 故障排查

| 现象 | 处理 |
|---|---|
| `permission denied … docker.sock` | 执行 `newgrp docker`，或使用 `sg docker -c "make up"` |
| `ensurepip is not available` | 安装 `python3-venv` 后重建 `.venv` |
| API readiness 返回 503 | 查看 `make ps` 与响应中的 `checks[].detail`；对应依赖未就绪 |
| MinIO 启动失败 | 拉取 `cgr.dev/chainguard/minio:latest`，确认网络可访问 cgr.dev |
| Temporal UI 未就绪 | 等待 `temporal` 健康后自动重试；查看 `make logs` |
| 端口被占用 | 修改 `.env` 中对应端口或停止本机冲突进程 |
