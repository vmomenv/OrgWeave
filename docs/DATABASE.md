# 数据库设计（Phase 0）

## 1. 运行形态

- PostgreSQL 16（`pgvector/pgvector:pg16`）。
- 扩展：`vector`（pgvector 0.8.x）与 `pgcrypto`，由 `infra/postgres/init/01-extensions.sql` 在空卷初始化时创建。
- Alembic 初始迁移 `0001_phase0` 再次以 `IF NOT EXISTS` 保证 vector 存在。
- 应用连接使用 `postgresql+asyncpg://`，连接池 `pool_pre_ping`、连接超时 10 秒。

## 2. Phase 0 表

### `system_settings`

| 列 | 类型 | 说明 |
|---|---|---|
| `key` | `text` PK | 配置键 |
| `value` | `jsonb` NOT NULL DEFAULT `'{}'` | 配置值 |
| `updated_at` | `timestamptz` NOT NULL DEFAULT `now()` | 更新时间 |

仅用于平台级基础设置。**它不是租户表**，不承担业务数据。

## 3. 迁移管理

```bash
make migrate                       # alembic upgrade head
make migrate-down                  # 回退一步
cd apps/api && ../../.venv/bin/alembic current
```

- 所有结构变更必须通过 Alembic，不允许手工改生产库。
- `vector` 扩展不在 downgrade 中删除，避免破坏未来依赖它的对象；由基础设施初始化负责。
- 迁移 URL 从 `OrgWeaveSettings` 读取，绝不从 `alembic.ini` 读取真实凭据。

## 4. Phase 1：多租户、组织与 RLS（已实现）

迁移 `0002_phase1` 创建：

- `users`、`refresh_tokens`（全局认证表）。
- `tenants`（全局目录），`tenant_memberships`。
- `departments`（自引用层级 + 复合租户外键）。
- `members`（human/ai 统一，复合外键到部门/上级）。
- `permissions`、`roles`（全局模板）、`role_permissions`、`member_roles`。
- `invitations`、`audit_logs`。

RLS 实际配置：

- `tenant_memberships`、`departments`、`members`、`member_roles`、`invitations`、`audit_logs`
  启用 `ENABLE` + `FORCE ROW LEVEL SECURITY`。
- 策略使用 `nullif(current_setting('app.tenant_id', true), '')::uuid`。
- `tenant_memberships` 允许用户读取自己的成员关系（用于租户选择），写入仍需当前租户上下文。
- 审计表允许 `tenant_id IS NULL` 的全局事件，但只对事件 actor 可见。
- 应用连接角色 `orgweave_app`：`NOSUPERUSER NOBYPASSRLS`；迁移使用所有者角色。
- 每个请求事务通过 `set_config('app.user_id'/'app.tenant_id', ..., true)` 注入上下文。
- 租户创建与邀请接受通过 SECURITY DEFINER 函数完成，避免破坏 RLS 写策略。

应用查询约束：

1. 所有租户业务表包含 `tenant_id uuid NOT NULL`（已用于 Phase 1 各表）。
2. 主键使用 `(tenant_id, id)` 复合键或带 tenant 的复合唯一约束；跨表引用使用复合外键 `(tenant_id, other_id)`，保证租户一致性。
3. 每张租户表启用 `ROW LEVEL SECURITY`，策略比较 `tenant_id = current_setting('app.tenant_id', true)::uuid`。
4. 每个事务执行 `SET LOCAL app.tenant_id = '<uuid>'`；连接池归还连接时上下文不得泄漏。推荐在 session/transaction 开始时通过服务端认证身份注入，绝不信任客户端传入的 `tenant_id`。
5. 应用数据库账号**不得**拥有 `BYPASSRLS`；迁移账号与应用账号分离。
6. Agent 私有数据在 `tenant_id` 之外再使用 `agent_id` 隔离。

## 5. 事物边界与审计

- `session_scope` 仅在成功时提交，异常时回滚。
- 后续所有关键写操作必须在同一事务内写入审计/Outbox，避免“业务成功、事件丢失”。
- 对象存储中的文件不属于数据库事务，采用“先写元数据草稿 → 上传 → 标记完成”的状态机。

## 5.1 Phase 2 表（已实现）

- `groups`（channel/direct）、`group_members`（role、last_read_at）。
- `messages`（线程 parent、软删除、metadata）、`message_mentions`。
- `attachments`（MinIO object_key、上传者、大小、类型）。
- 全部启用 FORCE RLS；复合外键保证群、成员、消息、附件同租户。

## 5.2 Phase 3 表（已实现）

- `agent_configs`（模型别名、System Prompt、工具白名单、硬限制）。
- `agent_sessions`（独立 Session、parent_session_id、control_mode、用量）。
- `agent_runs`（queued/running/completed/failed/cancelled、limits、steps、用量）。
- `agent_session_messages`（user/assistant/tool 消息与 tool_calls）。
- `agent_tool_calls`（参数、结果、状态、错误、时间）。
- `agent_memories`（5 类记忆、重要度、来源 Session）。
- 全部启用 FORCE RLS，复合外键保证同租户。

## 6. 后续数据模型（规划）

完整模型包括 tenants、users、tenant_memberships、members、departments、roles、permissions、agents、agent_sessions、agent_runs、agent_memories、agent_*、groups、messages、goals、tasks、skills、automations、audit_logs、outbox_events 等，详见实现总指令第十二章。Phase 0 不提前建表，避免在租户模型未定时产生不可逆迁移。
