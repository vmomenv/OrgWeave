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

## 4. Phase 1 规划：多租户与 RLS

Phase 0 **未创建任何业务表**，以下为 Phase 1 必须遵守的约束：

1. 所有租户业务表包含 `tenant_id uuid NOT NULL`。
2. 主键使用 `(tenant_id, id)` 复合键或带 tenant 的复合唯一约束；跨表引用使用复合外键 `(tenant_id, other_id)`，保证租户一致性。
3. 每张租户表启用 `ROW LEVEL SECURITY`，策略比较 `tenant_id = current_setting('app.tenant_id', true)::uuid`。
4. 每个事务执行 `SET LOCAL app.tenant_id = '<uuid>'`；连接池归还连接时上下文不得泄漏。推荐在 session/transaction 开始时通过服务端认证身份注入，绝不信任客户端传入的 `tenant_id`。
5. 应用数据库账号**不得**拥有 `BYPASSRLS`；迁移账号与应用账号分离。
6. Agent 私有数据在 `tenant_id` 之外再使用 `agent_id` 隔离。

## 5. 事物边界与审计

- `session_scope` 仅在成功时提交，异常时回滚。
- 后续所有关键写操作必须在同一事务内写入审计/Outbox，避免“业务成功、事件丢失”。
- 对象存储中的文件不属于数据库事务，采用“先写元数据草稿 → 上传 → 标记完成”的状态机。

## 6. 数据模型（规划）

完整模型包括 tenants、users、tenant_memberships、members、departments、roles、permissions、agents、agent_sessions、agent_runs、agent_memories、agent_*、groups、messages、goals、tasks、skills、automations、audit_logs、outbox_events 等，详见实现总指令第十二章。Phase 0 不提前建表，避免在租户模型未定时产生不可逆迁移。
