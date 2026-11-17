# 技术决策记录（ADR Log）

## ADR-008：认证与租户上下文（Phase 1）

- **决策**：JWT access token（15 分钟）+ 持久化 refresh token（30 天，数据库保存哈希）。Access token 只含 `sub`（user id）、`jti`、类型与过期时间，不含租户。
- 每个租户请求必须携带 `X-Tenant-ID`；服务端校验 `tenant_memberships` 后，将会话切换到该租户并执行 `SET LOCAL app.tenant_id`。客户端提供的 tenant 仅作为“选择”，权限由服务端派生。
- **原因**：避免租户被固化进令牌导致切换复杂，同时保证服务端不信任客户端租户字段。
- **替代方案**：登录时签发租户限定 token。被否，因为一个用户可加入多个租户，切换需重新登录。

## ADR-009：密码与令牌存储

- 密码使用 Argon2id 哈希；refresh token 仅存 SHA-256 哈希，原文只返回一次。
- 不引入外部身份提供商（Phase 1 范围）。
- 所有登录失败统一返回同一错误，避免账号枚举。

## ADR-010：RLS 策略

- 租户业务表全部启用 `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`。
- 策略读取 `current_setting('app.tenant_id', true)`；应用事务开始时 `SELECT set_config('app.tenant_id', :tenant_id, true)`。
- 应用使用非超级用户 `orgweave_app`（无 `BYPASSRLS`）；迁移使用 `orgweave` 所有者角色。
- 测试必须验证：跨租户查询返回 404/空；连接归还后上下文不残留。

## ADR-011：组织模型

- `Member` 统一 human/ai；human 关联 `user_id`，ai 关联 `agent_profile`（Phase 3 完整 Agent 配置）。
- 部门使用邻接表 `parent_id`；同租户复合外键 `(tenant_id, parent_id)`。
- 角色权限使用 `permissions` 全局字典 + 租户内 `roles` + `role_permissions`；成员通过 `member_roles` 多对多。
- AI 开关保存在 member/agent 配置，关闭后保留身份与历史（Phase 3 执行）。

## ADR-012：API 分页与错误格式

- 列表接口默认 `limit=50`，最大 200，使用 `offset` 分页（Phase 1 数据量小）。
- 业务错误统一 `{ "error": { "code", "message", "details" } }`，HTTP 401/403/404/409/422。
- 所有响应包含 `x-request-id`。

## ADR-013：Agent 委派执行策略

- `delegate_task` 默认同步：父 Run 的工具调用创建独立子 Session/Run，提交后使用独立数据库
  Session 执行子 Run，完成后返回结构化结果；支持 `wait=false` 入队异步执行。
- 服务端强制：同租户、目标 AI 启用、非自身、`allowed_agent_ids` 白名单、层级上限。
- 子 Session 与父 Session 上下文隔离，只通过任务描述与结构化结果交换。
- 子 Run 结束由 `finalize_delegations` 更新委派状态并向父 Session 写入系统通知。
- 权衡：同步委派简化 MVP 结果聚合；生产大规模并发应改用 Temporal 工作流并限制 Worker 递归。
