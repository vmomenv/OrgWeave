# OrgWeave 实施状态

> 本文件是跨会话恢复进度的唯一事实来源。每次开始工作先读这里。
> 更新时间：2026-11-17

## 当前阶段

**Phase 3：Agent Runtime、Session、Memory、Tool Calling —— 下一步**

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

### Phase 2（已完成，已验证）

- [x] 群组（channel）与单聊（direct，自动去重）
- [x] 群成员增删、群主保护
- [x] 文本消息、线程回复、搜索、未读数、已读
- [x] @成员与 @AI 提及（服务端解析并记录）
- [x] 文件附件上传（10 MiB、类型白名单、对象存储）与权限校验下载
- [x] WebSocket 租户鉴权、群事件实时广播、resubscribe
- [x] 前端群聊界面（会话列表、消息、提及、附件）
- 验证：59 passed；Phase 2 验收脚本 9/9。

## 进行中

- 准备 Phase 3：Agent 配置、Session/Run、模型调用、工具、记忆、执行限制。

## 下一步

Phase 3 依赖顺序：Agent 配置与 Session/Run 模型 → LiteLLM 客户端 → 工具调用循环 →
记忆 → Agent Worker 执行 → API/前端工作现场 → 模型联调与测试。
注意：当前环境无模型 Key/Ollama，真实模型调用验收需人工提供凭据。

## 未解决问题

- 当前环境没有可用的真实模型供应商 API Key，也没有本地 Ollama。Phase 3 的真实模型调用验收需要用户提供凭据或启动本地模型服务；在此之前可完成 Runtime/工具/委派实现与确定性工具测试，但不能声称 MVP 模型调用已验收。
- 角色目前为全局系统模板（owner/admin/member），租户自定义角色在后续阶段补充。
- 头像上传和成员搜索分页为简化实现。
- 生产部署、外部消息发送、付费 API 调用需人工授权。

## 已知风险

- RLS 需使用 `FORCE ROW LEVEL SECURITY` 并验证连接池上下文不泄漏。
- 前端认证状态需避免将 token 写入 URL 或日志。
