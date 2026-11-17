# 安全基线（Phase 0）

Phase 0 只建立基础设施安全底座。以下明确区分**已实施**与**待实施**。

## Phase 1 已实施

- Argon2id 密码哈希；JWT access token 15 分钟；refresh token 仅存 SHA-256 哈希并轮换。
- 前端令牌存储在 httpOnly + SameSite=Lax Cookie，不写入 localStorage；写操作 BFF 校验 Origin。
- 非超级用户 `orgweave_app`（NOBYPASSRLS）+ FORCE RLS；租户上下文服务端派生。
- RBAC 权限检查在路由依赖层执行；最后一名 Owner 不可被移除。
- 邀请令牌只返回一次，数据库存哈希，按邮箱绑定，接受时校验过期与邮箱。
- 审计记录登录、租户创建、部门/成员/角色/邀请变更。
- WebSocket 必须携带有效 access token，否则关闭 4401。

## Phase 0 已实施

1. **密钥不入库**：`.env` 被 `.gitignore` 与 `.dockerignore` 排除；`.env.example` 只含开发占位值。
2. **非 root 容器**：API、Web、全部 Worker 镜像以 uid 10001 运行。
3. **不暴露 Docker Socket**：Compose 未挂载 `/var/run/docker.sock`；Skill Runner 没有执行端点。
4. **依赖隔离**：API 与 Worker 通过 Redis/HTTP/数据库交互，Agent Worker 不直连数据库（Phase 0 无数据库访问）。
5. **健康信息脱敏**：探针异常信息中 URL 的 userinfo 被替换为 `***`。
6. **帧大小限制**：WebSocket 单帧 8 KiB。
7. **无假密钥**：LiteLLM 使用本地 Ollama 别名，未伪造供应商 Key。
8. **请求追踪**：每个 HTTP 响应带 `x-request-id`。
9. **配置校验**：启动时校验数据库/Redis URL scheme，避免误连错误服务。
10. **审计与最小权限**：Phase 0 无业务写操作；后续所有写操作必须审计。

## 待实施（按阶段）

| 阶段 | 安全要求 |
|---|---|
| Phase 2 | WebSocket 房间订阅鉴权与消息广播权限 |
| Phase 3 | Agent 工具与委派权限 |
| Phase 3 | Task Contract 服务端校验；模型不可扩权；工具调用二次授权 |
| Phase 3 | 模型 Key 仅存安全凭据存储；不进入 Prompt/日志 |
| Phase 5 | Skill Runner 文件系统/网络/CPU/内存/时间隔离；不可信代码不得运行在 API 进程 |
| Phase 5 | MCP Server 白名单、凭据隔离与审计 |
| Phase 7 | 接管/终止全量审计；高风险操作审批 |
| Phase 8 | Webhook 签名校验、幂等键、重放防护 |

## 威胁模型要点

- **模型输出不可信**：所有工具参数、委派目标、权限范围都由服务端校验，不能靠 Prompt 约束。
- **客户端 tenant_id 不可信**：必须从认证身份推导。
- **连接池租户上下文泄漏**：Phase 1 使用 `SET LOCAL`，并配合事务级重置与集成测试。
- **子 Agent 不得继承超额权限**：委派时对 Task Contract 取交集。
- **外部副作用不可假设可回滚**：接管/终止必须记录“是否已产生副作用”。

## 报告安全问题

请勿在公开 Issue 中粘贴密钥或生产数据。Phase 0 仓库尚无正式披露渠道，接入生产前必须补充 `SECURITY.md` 中的联系流程。
