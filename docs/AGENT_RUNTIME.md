# Agent Runtime 设计

> **实现状态：未实现。** Phase 0 仅提供 Agent Worker 进程骨架、任务 envelope、Redis 队列、死信与心跳。本文描述后续必须遵守的设计边界，不能作为“功能已完成”的依据。

## 1. 身份与执行分离

必须严格区分：

| 概念 | 含义 |
|---|---|
| Agent Member | 长期存在的 AI 员工（身份、岗位、权限、记忆） |
| Agent Session | 一次具体工作会话，可父子嵌套 |
| Agent Run | Session 内一次模型/工具执行过程 |
| Task | 正式任务，受 Task Contract 约束 |
| Delegation | 员工之间的委派关系 |

同一 Agent 可拥有多个 Session；每次任务/委派创建独立 Session，禁止直接共享父上下文。

## 2. Phase 0 已落地的骨架

- Redis 列表 `orgweave:agent:jobs` 消费任务。
- `AgentJob` envelope（`job_id`、命名空间 `type`、`payload`、`attempts`）。
- 仅支持 `system.ping`；非法或未支持任务进入 `orgweave:agent:dead-letter`，不会静默丢弃。
- 成功结果写入 `orgweave:agent:results`。
- Worker 心跳 `/orgweave:worker/agent-worker/heartbeat`。
- Temporal Worker 注册 `PingWorkflow` 任务队列 `orgweave-phase0`，用于证明工作流链路。

这些是**传输与生命周期骨架**，不是 Agent Runtime。

## 3. 规划的执行流程

1. 接收任务并验证 tenant、Agent 身份、任务分配关系。
2. 加载 Task Contract、授权企业知识、Agent 长期记忆、Session 上下文、已安装 Skills、可用 Tools。
3. 构建模型上下文（模型通过 LiteLLM 别名调用）。
4. 解析响应；在每次工具执行前做服务端二次授权。
5. 记录工具调用、token/费用、执行事件；结果写回 Session。
6. 判断继续、委派、完成；应用步数/时间/预算/并发/取消限制。
7. 形成交付物并更新任务状态、通知群聊与相关人员。

## 4. 硬性限制

每次 Run 必须由服务端强制：`max_steps`、`max_duration`、`token_budget`、`cost_budget`、`max_tool_calls`、`max_consecutive_failures`、`max_child_agents`、`max_delegation_depth`、`max_concurrency`。**达到限制时不能只写数据库状态，必须在执行路径上阻断。**

## 5. 记忆

- 按 `tenant_id` + `agent_id` 隔离；检索前做权限检查。
- 类型：Profile / Semantic / Episodic / Task / Procedural。
- 共享知识必须通过显式企业知识库授权，不能默认读取其他 Agent 私有记忆。

## 6. 模型网关

- 统一经 LiteLLM；使用模型别名，不硬编码供应商。
- 支持超时、重试、限流、预算与用量记录。
- Key 存安全凭据，不写 Prompt、日志或普通字段。

## 7. 验收（Phase 3）

创建一个 AI 员工，能接收任务、在多轮中调用授权工具、产生可审计的工具记录与交付物，并能在超出限制时被服务端中止。
