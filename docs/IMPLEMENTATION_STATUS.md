# OrgWeave 实施状态

> 本文件是跨会话恢复进度的唯一事实来源。每次开始工作先读这里。
> 更新时间：2026-11-17

## 当前阶段

**Phase 2：群聊、消息与 WebSocket —— 下一步**

## 已完成

### Phase 0（已完成，已验证）

- Monorepo、Docker Compose（12 服务）、Makefile、CI、文档。
- API `/api/v1`、WebSocket `/ws/v1`、健康检查、Alembic 基线。
- 4 个 Worker 骨架、心跳、死信、Temporal PingWorkflow。
- 测试：44 passed；`make verify` 20/20。

### Phase 1（已完成，已验证）

- [x] 项目状态/决策/测试报告文档建立
- [x] 用户认证（注册、登录、刷新、登出、me）
- [x] Tenant + TenantMembership + 租户选择
- [x] 部门（层级、循环检测）
- [x] Member（human / ai）
- [x] Role + Permission + Member 角色
- [x] RLS 与租户上下文（非超级用户应用角色）
- [x] 组织管理 API
- [x] 登录/租户/组织管理前端（httpOnly Cookie BFF）
- [x] 邀请成员
- [x] 跨租户隔离测试
- [x] 前端构建与文档更新
- 验证：54 passed；Phase 1 验收脚本 13/13。

## 进行中

- 准备 Phase 2：群聊、消息、成员管理、WebSocket 实时事件。

## 下一步

Phase 2 依赖顺序：数据库模型/迁移 → 群组与消息 API → WebSocket 房间鉴权/广播 →
前端群聊界面 → 测试与文档。之后进入 Phase 3 Agent Runtime。

## 未解决问题

- 当前环境没有可用的真实模型供应商 API Key，也没有本地 Ollama。Phase 3 的真实模型调用验收需要用户提供凭据或启动本地模型服务；在此之前可完成 Runtime/工具/委派实现与确定性工具测试，但不能声称 MVP 模型调用已验收。
- 角色目前为全局系统模板（owner/admin/member），租户自定义角色在后续阶段补充。
- 头像上传和成员搜索分页为简化实现。
- 生产部署、外部消息发送、付费 API 调用需人工授权。

## 已知风险

- RLS 需使用 `FORCE ROW LEVEL SECURITY` 并验证连接池上下文不泄漏。
- 前端认证状态需避免将 token 写入 URL 或日志。
