# OrgWeave 实施状态

> 本文件是跨会话恢复进度的唯一事实来源。每次开始工作先读这里。
> 更新时间：2026-11-17

## 当前阶段

**MVP Checkpoint：四 AI 员工完成真实软件开发任务 —— 下一步**

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

### Phase 3（已完成，已验证，含真实模型 E2E）

- [x] AgentConfig（System Prompt、模型别名、温度、工具白名单、所有硬限制）
- [x] Agent Session / Run / Session 消息 / Tool Call / Memory 数据模型与 RLS
- [x] LiteLLM OpenAI 兼容客户端（超时/错误脱敏）
- [x] 工具调用循环：get_current_time、list_team_members、remember、search_memory
- [x] 服务端硬限制：max_steps、max_tool_calls、max_duration、token budget、连续失败
- [x] 取消（Redis 取消键 + queued 直接取消）与 Worker 执行适配
- [x] 工具调用审计、会话消息持久化、完成后写入 Episodic Memory
- [x] API：agents/sessions/runs/tools/memories
- [x] 前端 AI 员工工作台（会话、执行、工具调用、记忆、配置）
- [x] 测试：66 passed；含真实 Worker 适配器与工具循环、限制、取消、会话隔离
- 真实模型端到端：Ollama qwen2.5:1.5b → LiteLLM → Agent Worker → get_current_time 工具
  → 最终回答，`ORGWEAVE_MODEL_E2E=1` 验收 9/9。

### Phase 4（已完成，已验证，含真实模型 E2E）

- [x] AgentConfig 委派策略（allowed_agent_ids、max_delegation_depth）
- [x] agent_delegations 表、RLS、父子 Session 关联
- [x] 服务端授权：目标必须同租户、AI 启用、非自身、白名单、层级限制
- [x] 工具：list_available_agents、delegate_task、get_task_status、get_task_result、
      send_message_to_agent、request_agent_review、cancel_delegated_task
- [x] 同步委派（子 Run 立即执行并返回结果）与异步委派（入队 + 后续查询）
- [x] 子 Session 独立上下文；完成后 Delegation 更新并向父 Session 写入通知
- [x] API：Session delegations/children、Delegation 详情；前端委派卡片
- [x] 真实模型 E2E：CTO-AI 调用 delegate_task → Researcher-AI 独立 Session → 结果回传
- 验证：69 passed；Phase 4 验收 13/13。

## 进行中

- MVP Checkpoint：CTO/Researcher/Developer/QA 四员工完成一个真实软件开发任务。

## 下一步

MVP 需要：任务/目标下发（可先用 Session + 委派）、真实代码交付工具（文件写入 Sandbox/对象存储）、
QA 执行真实测试、CTO 汇总。当前工具仅有组织/记忆/委派，需要新增代码交付与测试工具。

## 未解决问题

- 开发/测试统一使用外部模型网关；当前缺少外部网关 URL/Key，真实模型 E2E 暂停等待凭据。
- 角色目前为全局系统模板（owner/admin/member），租户自定义角色在后续阶段补充。
- 头像上传和成员搜索分页为简化实现。
- 生产部署、外部消息发送、付费 API 调用需人工授权。

## 已知风险

- RLS 需使用 `FORCE ROW LEVEL SECURITY` 并验证连接池上下文不泄漏。
- 前端认证状态需避免将 token 写入 URL 或日志。
