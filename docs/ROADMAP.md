# OrgWeave 路线图

## Phase 0：项目基础设施 — ✅ 已完成

交付：

- Monorepo：`apps/api`、`apps/web`、`workers/*`、`packages/*`、`infra/*`、`docs/*`、`scripts/*`。
- Next.js 15 控制台（实时健康状态、主题切换、服务入口）。
- FastAPI `/api/v1` + `/ws/v1`、OpenAPI、请求 ID、CORS。
- PostgreSQL 16 + pgvector、Redis、Temporal、LiteLLM、MinIO。
- 4 个 Worker 骨架与真实心跳、Agent 任务死信、Temporal PingWorkflow。
- Alembic 基线（vector + `system_settings`）。
- pytest 单元/集成测试、Ruff、ESLint、TypeScript、CI、Makefile、文档。

验收证据：`make verify`（Compose 配置、5 项依赖、数据库迁移、44 个测试、前端构建、Temporal 冒烟）。

---

## Phase 1：组织与租户 — ✅ 已完成

范围：

1. 用户注册/登录、密码哈希、会话/刷新令牌。
2. Tenant、TenantMembership；服务端 tenant 上下文。
3. 部门层级、Member（human/ai 统一模型）、Role、Permission。
4. 租户表 `tenant_id` + 复合外键 + RLS + `SET LOCAL app.tenant_id`。
5. 基础管理界面：租户选择、组织架构、部门、成员。
6. WebSocket 鉴权与租户隔离。
7. 审计日志基础设施（登录、租户切换、权限变更、成员操作）。
8. 集成测试：不同租户无法互访；连接池不泄漏租户上下文。

验收：两个租户互相不可见；RLS 在应用账号下真实生效。

实施结果（2026-11-17）：

- JWT access + 持久化 refresh token 轮换；Argon2id 密码哈希。
- 非超级用户 `orgweave_app` + FORCE RLS；用户/租户/部门/成员/RBAC/邀请/审计。
- 前端：登录/注册、租户选择与创建、组织成员、部门、角色、邀请、审计。
- 测试：54 passed；`scripts/verify-phase1.sh` 13/13；Next.js 构建通过。
- 主要限制：角色为全局模板（自定义租户角色留待后续）；文件头像上传未实现。

---

## Phase 2：群聊与消息 — ✅ 已完成

单聊/群聊、成员管理、@成员/@AI、线程、附件、已读、搜索、WebSocket 实时。

验收：普通群聊不自动触发所有 AI；只有明确 @ / 正式任务 / 自动化事件才启动 Agent。

实施结果（2026-11-17）：

- groups/group_members/messages/message_mentions/attachments + RLS。
- 单聊自动去重、群成员权限、线程回复、搜索、未读/已读。
- 服务端解析 @显示名 记录 AI 提及；不自动执行 AI（Agent Runtime 在 Phase 3）。
- MinIO 附件上传/下载（权限校验 + 大小/类型限制）。
- WebSocket 租户鉴权、群事件 Redis 广播、resubscribe。
- 前端群聊面板与实时状态。
- 测试：59 passed；Phase 2 验收 9/9。

已知限制：移除群成员对已建立 WebSocket 连接在重连后才生效；附件仅单文件上传。

## Phase 3：Agent Runtime — ✅ 已完成（含真实模型 E2E）

Agent 配置、Session/Run、模型调用、工具、上下文、记忆、执行限制、状态管理。

验收：AI 员工接收任务并调用真实工具，产生审计与交付物。

实施结果（2026-11-17）：

- Agent 配置、独立 Session、Run、会话消息、工具调用、记忆（RLS）。
- LiteLLM 客户端 + 4 个内置工具 + 服务端硬限制与取消。
- Agent Worker 消费 `agent.run` 队列，真实执行工具循环。
- API + AI 员工工作台前端。
- 测试：66 passed（确定性 OpenAI 兼容服务验证循环/限制/取消/Worker）。
- 真实模型端到端：Ollama qwen2.5:1.5b + LiteLLM + Worker + 工具调用，9/9 通过。

## Phase 4：Agent Delegation（下一步）

员工调用员工、独立 Child Session、异步/并行/依赖/取消/结果回传、委派权限。

验收：CTO 调用 Researcher、Developer、QA 完成有实际交付物的任务。

## Phase 5：Skills 与工具生态

Skill Registry/Version、安装与启用、隔离 Skill Runner、MCP、权限与审计。

验收：不同 Agent 安装不同 Skills，权限互不混淆。

## Phase 6：Goals & Tasks

目标拆解、任务分配、依赖、Task Contract、审批、交付物、进度。

验收：高层目标由 AI 团队自主拆解并完成。

## Phase 7：Watchdog & Human Takeover

Observe/Guide/Takeover/Kill、循环/预算/越权检测、告警、Snapshot、管理员现场、审计。

验收：管理员发现循环后暂停并接管/终止，执行路径真正被阻断。

## Phase 8：Automation

Cron、Webhook、Event Trigger、Temporal 工作流、幂等、重试、执行历史、失败通知。

验收：AI 员工按时间或事件自动启动任务。

---

## 推进规则

- 每阶段完成后：运行测试、更新文档、记录真实结果，再进入下一阶段。
- 不允许以 Mock 或数据库状态伪装功能完成。
- 关键架构决策记录在 `docs/ARCHITECTURE.md`（ADR）。
