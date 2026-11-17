# 测试报告

> 只记录实际执行过的命令和结果。环境：本机 Docker Compose，2026-11-17。

## Phase 1（当前）

### 后端测试

```bash
ORGWEAVE_INTEGRATION=1 .venv/bin/python -m pytest -q
# 54 passed, 1 warning（Starlette TestClient 的第三方弃用警告）
```

覆盖范围：

- 注册、登录、刷新令牌轮换、复用旧 refresh token 拒绝、登出。
- 重复邮箱、错误密码。
- 租户创建、租户列表、`X-Tenant-ID` 上下文、Owner 权限集合。
- 缺少租户头 → 400；非成员租户 → 403；隐藏租户详情 → 404。
- 部门创建/层级/循环检测/成员存在时禁止删除。
- AI 成员创建与角色、人类成员绑定、重复成员冲突。
- RBAC：member 角色越权 403；Owner 提升为 admin 后操作成功；最后 Owner 保护。
- 邀请：创建、邮箱不匹配拒绝、接受、重复接受拒绝。
- 审计事件写入与读取。
- 未认证/非法 Token。
- 认证 WebSocket：无 Token 拒绝，有效 Token 握手与 ping/pong。
- **RLS（真实非超级用户 orgweave_app）**：不同租户只能看到自己的数据；无租户上下文返回 0 行；跨租户 INSERT 被 WITH CHECK 拒绝。

### Phase 1 验收脚本

```bash
bash scripts/verify-phase1.sh
# Phase 1 verification: 13 passed, 0 failed
```

包含：注册 → 创建租户 → Owner 权限 → 创建部门/AI 员工 → 邀请并接受 → 外部用户越权 403 → 审计 → Web 登录页/工作空间页 200。

### 前端检查

```bash
pnpm --filter @orgweave/web typecheck   # 通过
pnpm --filter @orgweave/web lint        # 0 errors
pnpm --filter @orgweave/web build       # 通过，10 条路由
```

### 手工端到端（Next.js BFF + httpOnly Cookie）

```text
POST /api/auth/register            -> 201 + Set-Cookie (httpOnly)
GET  /api/auth/me                  -> 200
POST /api/proxy/tenants            -> 201
GET  /api/proxy/tenant             -> 200 (owner 权限)
POST /api/proxy/departments        -> 201
POST /api/proxy/members            -> 201 (AI CTO, admin)
GET  /api/proxy/members            -> 200 (owner + AI 两名成员)
```

### 数据库迁移

```bash
cd apps/api && ../../.venv/bin/alembic upgrade head
# 0001_phase0 -> 0002_phase1 成功
```

迁移包含：users、refresh_tokens、tenants、tenant_memberships、departments、members、
permissions、roles、role_permissions、member_roles、invitations、audit_logs，
RLS 策略，以及 `orgweave_create_tenant` / `orgweave_accept_invitation` 两个
SECURITY DEFINER 函数。

## Phase 0（历史）

```text
docker compose config -q       PASS
make verify                    20 passed, 0 failed
pytest                         44 passed
Temporal PingWorkflow          OK
四 Worker 心跳                  OK
```

## 尚未验证 / 阻塞

- Phase 2+ 尚未实现。
- 真实模型调用（Phase 3 MVP）缺少供应商 API Key / 本地 Ollama；尚未验收。
- 生产 HTTPS Cookie（`COOKIE_SECURE=true`）、生产数据库角色分离未在本机验收。
