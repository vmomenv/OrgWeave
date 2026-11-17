# OrgWeave — AI Organization Operating System
## Implementation Master Prompt

你现在是 OrgWeave 项目的首席架构师、技术负责人和全栈工程师。

你需要负责将 OrgWeave 从零构建为一个真正可运行、可扩展、安全、支持多租户的 AI 企业组织协作平台。

不要把它做成普通的 AI 聊天网站，也不要做成简单的多 Agent Demo。

本项目的核心理念是：

**让 AI 成为组织中的真实成员，让 AI 员工拥有身份、岗位、权限、记忆、技能、工作空间和协作关系，让多个 AI 员工像真实团队一样共同完成工作，同时允许人类管理员随时观察、干预和接管。**

---

# 一、产品定义

项目名称：OrgWeave

产品类型：AI Organization Operating System

核心定位：

一个以组织架构为基础，以 AI 员工为执行主体，以人类管理员为监督和控制中心的多租户 AI 企业操作系统。

产品整体交互参考飞书、Slack 等企业协作软件，但核心能力从人与人协作扩展为人与 AI 员工、AI 员工与 AI 员工之间的协作。

产品必须支持：

1. 多租户企业组织。
2. 真实人类成员。
3. AI 员工。
4. 部门、岗位和组织架构。
5. 群聊、私聊和消息系统。
6. AI 员工自主执行任务。
7. AI 员工之间委派任务。
8. Agent 独立 Session 和上下文。
9. Agent 私有记忆数据库。
10. Skills 安装和执行。
11. MCP 和外部工具集成。
12. 目标管理和任务拆解。
13. 定时任务和事件触发。
14. AI 员工运行监控。
15. Watchdog 异常检测。
16. 管理员人工干预和接管。
17. 多模型统一接入。
18. 完整审计与权限管理。

产品首先服务于多租户企业，但架构应允许后续扩展为个人组织、团队组织和大型企业组织。

---

# 二、核心产品设计

## 2.1 多租户组织架构

每个企业是一个 Tenant。

一个登录用户可以加入多个 Tenant。

系统必须区分：

- User：真实登录账户。
- Tenant：企业租户。
- TenantMembership：用户在企业中的成员关系。
- Member：企业组织中的成员实体。
- Department：部门。
- Role：岗位或组织角色。
- Permission：权限。

Member 统一表示人类和 AI 员工：

member_type:
- human
- ai

人类 Member 关联 User。

AI Member 关联 Agent 配置。

一个租户可以有多个部门、多个岗位、多个 AI 员工。

AI 员工应与真实员工一样出现在组织架构、成员列表、群聊和任务系统中。

支持：
- 新建部门。
- 部门层级。
- 添加真实成员。
- 邀请成员。
- 创建 AI 员工。
- 设置员工头像、名称、岗位和简介。
- 配置 AI 员工所属部门。
- 配置员工上下级关系。
- 设置员工状态。
- 停用和删除员工。
- 查看员工工作历史。

创建 AI 员工时，应提供 AI 开关。

关闭 AI 开关后，该成员不再由 Agent Runtime 自主执行工作，但历史记录和身份资料应保留。

## 2.2 AI 员工

每个 AI 员工必须拥有独立配置：

- 员工身份。
- 岗位职责。
- System Prompt。
- 工作目标。
- 模型配置。
- 模型参数。
- 工具权限。
- Skills。
- MCP Servers。
- 长期记忆。
- 工作会话。
- 任务历史。
- 预算。
- 执行限制。
- 可委派员工。
- 可访问数据范围。

AI 员工不只是一个 Prompt。

它是一个长期存在的组织成员，可以反复接受任务、持续积累授权记忆，并在不同工作会话中执行工作。

---

# 三、Agent Runtime：核心执行引擎

必须自行建设 OrgWeave Agent Runtime。

可以借鉴 OpenCode 的 Agent、Subagent、Session、Tool Calling、Permission、Background Execution 等机制。

但不要将 OpenCode 作为整个产品运行时的强制依赖。

OrgWeave 必须拥有自己的 Agent Runtime。

## 3.1 Agent Identity 与 Session 分离

必须区分：

- Agent Member：长期存在的 AI 员工。
- Agent Session：一次具体的工作会话。
- Agent Run：一次具体执行过程。
- Task：正式任务。
- Delegation：员工之间的委派关系。

同一个 AI 员工可以拥有多个 Session。

每次独立工作应创建对应 Session。

每次委派任务应创建 Child Session。

Session 必须记录：
- tenant_id
- agent_id
- parent_session_id
- task_id
- status
- control_mode
- context_summary
- model
- token_usage
- cost_usage
- started_at
- completed_at

父 Session 和子 Session 必须能够构成完整的调用关系树。

## 3.2 Agent 执行流程

标准 Agent Runtime 流程：

1. 接收任务。
2. 验证 Tenant。
3. 验证 Agent 身份。
4. 验证任务分配关系。
5. 加载 Task Contract。
6. 加载授权的企业知识。
7. 加载 Agent 长期记忆。
8. 加载当前 Session 上下文。
9. 加载已安装 Skills。
10. 加载可用 Tools。
11. 构建模型上下文。
12. 调用模型。
13. 解析模型响应。
14. 检查工具权限。
15. 执行工具。
16. 保存工具调用记录。
17. 将结果加入当前 Session。
18. 判断是否需要继续执行。
19. 判断是否需要委派子任务。
20. 完成任务并形成交付物。
21. 更新任务状态。
22. 通知群聊和相关人员。

每一次执行都必须有步骤上限、时间限制、预算限制、并发限制和取消机制。

## 3.3 Task Contract

每一个正式任务必须拥有 Task Contract。

至少包含：

- task_id
- tenant_id
- assigned_agent_id
- parent_task_id
- objective
- expected_deliverables
- allowed_tools
- allowed_agents
- allowed_data_scopes
- max_steps
- max_duration
- token_budget
- cost_budget
- max_delegation_depth
- approval_required
- expiration_time

Agent 只能在 Task Contract 允许的范围内执行。

不能通过修改 Prompt、重新调用模型或委派子 Agent 绕过任务权限。

---

# 四、Agent Delegation：员工之间的委派系统

这是 OrgWeave 的核心能力之一。

参考 OpenCode Subagent 机制，但将其升级为企业员工之间的协作系统。

## 4.1 委派能力

每个 AI 员工可以在授权范围内调用其他 AI 员工。

提供标准工具：

- list_available_agents
- delegate_task
- get_task_status
- get_task_result
- send_message_to_agent
- request_agent_review
- cancel_delegated_task

AI 员工可以根据任务需要自行决定是否委派工作。

委派必须通过服务端授权检查。

不得让模型自行指定一个任意 Agent ID 并直接执行。

## 4.2 委派过程

例如：

用户向 CTO 下达任务：

开发一个 IT 资产管理系统。

CTO 可以：

1. 分析目标。
2. 制定项目计划。
3. 调用 Researcher 调研需求。
4. 调用 Architect 设计架构。
5. 调用 Developer 实施开发。
6. 调用 QA Engineer 测试。
7. 汇总结果。
8. 向用户交付软件。

父 Agent 可以同时运行多个子任务。

如果某个任务依赖其他任务，应建立任务依赖关系。

## 4.3 Session 隔离

每个子 Agent 必须拥有独立 Session。

不得直接共享父 Agent 的完整上下文。

父 Agent 通过任务描述、授权信息、必要背景和交付物与子 Agent 交换信息。

子 Agent 完成任务后返回结构化结果：

- summary
- result
- artifacts
- issues
- recommendations
- status

## 4.4 并行与后台执行

支持：
- 同步委派。
- 异步委派。
- 后台执行。
- 并行任务。
- 任务依赖。
- 任务取消。
- 超时。
- 失败重试。

必须能够在 UI 中展示父子任务关系和执行状态。

---

# 五、Human Takeover：管理员人工接管系统

这是 OrgWeave 的核心差异化能力。

管理员必须能够观察、引导、接管和终止任何有权管理的 AI 员工工作会话。

接管对象是具体 Session 和 Run，而不是简单修改员工身份。

## 5.1 四种控制模式

Observe：

只读观察。

管理员可以查看：
- 当前任务。
- 当前执行步骤。
- 模型调用记录。
- 工具调用记录。
- 工具参数与结果。
- Token 使用量。
- 费用。
- 执行时间。
- 子 Agent。
- 任务状态。
- 错误和异常。

Guide：

引导模式。

管理员可以向 AI 注入新指令、修正目标、增加约束、要求重新规划。

Takeover：

人工接管。

管理员取得当前 Session 的控制权。

接管后：
- 暂停 AI 自主执行。
- 禁止新的模型请求。
- 禁止新的工具调用。
- 暂停新的子任务派发。
- 管理员可以向当前 Session 发送消息。
- 管理员可以修改任务计划。
- 管理员可以手动执行已授权工具。
- 管理员可以取消子任务。
- 管理员可以决定是否恢复 AI。

Kill：

紧急终止。

立即阻止新的模型调用和工具调用。

取消能够取消的执行任务。

停止新的委派。

记录无法撤销的外部副作用。

保存现场和审计记录。

## 5.2 接管控制器

建设统一 Takeover Controller。

不得只通过修改数据库状态实现暂停。

Agent Worker、Temporal Worker、Skill Runner 都必须支持执行控制。

使用执行控制令牌、Session 状态校验和工具调用前二次授权。

对于正在执行的外部操作：
- 明确是否支持取消。
- 明确是否已经产生外部副作用。
- 明确是否可以回滚。
- 记录取消结果。

管理员释放控制权后，Agent 只能基于最新任务状态恢复工作。

## 5.3 管理员人工操作

管理员接管期间：

- 可以代表该员工继续工作。
- 可以输入新的执行指令。
- 可以查看当前上下文摘要。
- 可以修改任务目标。
- 可以修改任务计划。
- 可以手动调用工具。
- 可以选择让 AI 从新的状态继续。
- 可以终止任务。

所有人工操作必须标记为 human_action，不能混淆为 AI 自主操作。

## 5.4 Session 检查点

支持创建 Session Snapshot。

管理员发现 AI 执行错误时，可以从历史检查点创建新的执行分支。

保留旧执行历史。

不要假设能够撤销已经产生的外部副作用。

---

# 六、Agent Watchdog：AI 员工异常监控

建立独立 Watchdog 服务。

持续监控所有 Agent Session 和 Agent Run。

## 6.1 异常识别

检测：

1. 重复工具调用。
2. 相似请求循环。
3. 长时间没有进展。
4. 连续工具失败。
5. Token 超预算。
6. 费用超预算。
7. 执行时间超限。
8. 子 Agent 数量过多。
9. 委派层级过深。
10. 工具调用频率异常。
11. 权限拒绝和越权尝试。
12. 任务依赖死锁。
13. Session 心跳丢失。

## 6.2 硬性限制

所有 Run 必须配置：

- max_steps
- max_duration
- token_budget
- cost_budget
- max_tool_calls
- max_consecutive_failures
- max_child_agents
- max_delegation_depth
- max_concurrency

达到限制必须由服务端拦截。

## 6.3 监控策略

基础安全机制必须使用确定性代码实现。

可以增加 AI 异常分析，但 AI 分析不能代替硬限制。

告警等级：

- info
- warning
- high
- critical

支持：
- 告警通知。
- 自动暂停。
- 自动终止。
- 管理员接管。
- 告警历史。
- 异常分析报告。

---

# 七、Skills 系统

Skills 是 AI 员工可安装和使用的能力模块。

参考 OpenCode Skills 的可发现、可加载和可复用设计。

但 OrgWeave 必须具备企业级权限与版本管理。

## 7.1 Skill 分类

公共 Skills：

平台维护。

tenant_id 为 NULL。

企业只能安装和使用，不能直接修改平台公共版本。

企业私有 Skills：

tenant_id 非空。

只能在所属租户范围内使用。

Agent 私有安装：

每个 Agent 可以独立安装 Skills。

使用 AgentSkill 记录：
- agent_id
- skill_id
- version_id
- installed_at
- configuration
- permission_grants
- enabled

## 7.2 Skill 生命周期

- 发现。
- 查看说明。
- 安装。
- 配置。
- 授权。
- 启用。
- 禁用。
- 更新。
- 卸载。

Skill 版本必须不可变。

更新时创建新版本。

## 7.3 Skill 安全

Skill 不能直接获得宿主机全部权限。

执行必须通过独立 Skill Runner。

不可信 Skill 必须隔离执行。

需要：
- 文件系统隔离。
- 网络访问限制。
- CPU 限制。
- 内存限制。
- 执行时间限制。
- 权限白名单。
- 审计日志。

不得向 API 或 Agent Worker 暴露宿主机 Docker Socket。

---

# 八、Memory：AI 员工独立记忆系统

每个 AI 员工拥有独立的长期记忆空间。

数据必须按 tenant_id 和 agent_id 隔离。

记忆类型：

- Profile Memory：员工身份、岗位和工作规范。
- Semantic Memory：长期知识。
- Episodic Memory：历史工作经验。
- Task Memory：当前任务相关记忆。
- Procedural Memory：工作流程和经验。

支持：
- 记忆写入。
- 记忆检索。
- 记忆更新。
- 记忆失效。
- 记忆删除。
- 记忆授权。
- 记忆来源追踪。

记忆检索必须检查访问权限。

不得将其他 Agent 的私有记忆默认暴露给当前 Agent。

共享知识必须通过明确的企业知识库授权实现。

---

# 九、群聊与消息系统

整体交互参考飞书。

支持：

- 单聊。
- 群聊。
- 人类成员。
- AI 员工。
- @成员。
- @AI 员工。
- 消息引用。
- 文件。
- 图片。
- 线程回复。
- 消息搜索。
- 实时状态。
- 已读状态。
- 消息历史。

特别要求：

普通群聊消息不应自动触发所有 AI 员工思考。

只有明确 @ 某个 AI 员工，或通过正式任务、自动化事件触发，才启动对应 Agent。

群聊中的普通聊天与正式任务必须区分。

当用户说“请研究一下”时，需要根据意图创建任务并确认授权，不能把所有普通消息自动当成任务。

AI 员工可以通过群聊发送工作进度、任务结果和异常通知。

---

# 十、Goals & Tasks：目标与任务管理

支持用户创建一个高层目标。

例如：

建立一个学校 IT 资产管理系统。

目标可以由 AI 员工分析和拆解。

支持：
- Goal。
- Task。
- Subtask。
- Task Dependency。
- Task Assignment。
- Task Contract。
- Task Review。
- Task Approval。
- Deliverables。
- Progress。
- Deadline。

任务状态：

- draft
- pending
- assigned
- running
- blocked
- waiting_approval
- completed
- failed
- cancelled

Agent 可以自主创建子任务，但必须受 Task Contract 限制。

---

# 十一、Automation：自动化系统

支持三种触发方式：

1. Cron 定时任务。
2. Webhook。
3. Event Trigger。

例如：

- 每天上午 9 点生成运营报告。
- 收到新邮件后触发 Researcher。
- 某个任务完成后自动通知 CTO。
- 某个服务异常时通知 IT AI 员工。
- 每周自动生成项目进度报告。

自动化必须具备：
- 幂等键。
- 重试。
- 执行历史。
- 权限检查。
- 审计记录。
- 失败通知。

使用 Temporal 处理长时间运行工作流。

---

# 十二、技术架构

采用模块化单体 + 独立 Worker 的架构。

第一阶段不采用复杂微服务架构。

所有业务模块先放在一个模块化后端中，Agent Worker、Skill Runner、Temporal Worker 独立部署。

## 12.1 Frontend

- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui
- React
- WebSocket

界面要求：
- 现代化企业 SaaS。
- 简洁。
- 专业。
- 高信息密度。
- 支持响应式布局。
- 支持深色和浅色主题。
- 不要过度使用渐变和装饰。
- 优先保证真实交互和可用性。

核心页面：

1. 登录。
2. 租户选择。
3. 工作台。
4. 组织架构。
5. 部门管理。
6. 成员管理。
7. AI 员工管理。
8. 群聊。
9. 任务中心。
10. 目标管理。
11. Skills 市场。
12. AI 员工工作现场。
13. AI Control Center。
14. 自动化管理。
15. 模型管理。
16. 审计日志。
17. 租户设置。
18. 平台管理后台。

## 12.2 Backend

- Python
- FastAPI
- SQLAlchemy 2.x
- Pydantic v2
- Alembic
- PostgreSQL
- pgvector
- Redis

使用 REST API 和 WebSocket。

所有 API 统一使用 /api/v1。

WebSocket 使用 /ws/v1。

后端采用清晰的模块分层：

- API。
- Application。
- Domain。
- Infrastructure。

避免把所有业务逻辑写在路由文件中。

## 12.3 Database

PostgreSQL 作为主要数据库。

使用 pgvector 支持向量检索。

核心数据模型包括：

- tenants
- users
- tenant_memberships
- members
- departments
- roles
- permissions
- agents
- agent_sessions
- agent_runs
- agent_memories
- agent_databases
- agent_relationships
- agent_delegations
- agent_permissions
- agent_tool_calls
- agent_artifacts
- agent_execution_events
- agent_takeovers
- agent_interventions
- agent_alerts
- groups
- group_members
- messages
- message_mentions
- goals
- tasks
- task_dependencies
- task_contracts
- skills
- skill_versions
- agent_skills
- automations
- automation_runs
- audit_logs
- outbox_events

可以根据实际实现进一步细化。

## 12.4 Tenant Isolation

采用逻辑隔离。

所有租户业务表必须有 tenant_id。

使用 PostgreSQL Row Level Security。

使用复合外键保证租户关系一致。

tenant_id 必须由服务端根据认证身份确定，不能信任客户端传入的 tenant_id。

每个事务中设置：

SET LOCAL app.tenant_id = '...';

注意连接池复用时不能泄漏租户上下文。

应用数据库账号不得绕过 RLS。

Agent 私有数据进一步使用 agent_id 隔离。

## 12.5 Model Gateway

统一使用 LiteLLM 作为模型网关。

Agent Runtime 不直接依赖某个模型供应商 SDK。

支持：
- OpenAI。
- Anthropic。
- Qwen。
- 兼容 OpenAI API 的模型。
- 本地模型服务。
- Ollama。
- 后续扩展其他供应商。

模型配置通过模型别名引用。

API Key 使用安全凭据存储，不得写入普通数据库字段或日志。

模型网关必须支持超时、重试、限流、预算和使用量记录。

## 12.6 Workflow Engine

使用 Temporal。

负责：
- Agent 长任务。
- Agent Delegation。
- 任务依赖。
- 自动化。
- 定时执行。
- 重试。
- 超时。
- 取消。
- 人工审批。
- 恢复执行。

Temporal 开发环境可以使用官方开发服务。

生产环境必须使用持久化部署，不能使用开发模式代替生产环境。

## 12.7 Storage

使用 MinIO 存储：

- 用户上传文件。
- AI 员工交付物。
- Skill 文件。
- 任务附件。
- 生成的报告。

文件访问必须校验租户和资源权限。

## 12.8 Worker

独立运行：

- Agent Worker。
- Temporal Worker。
- Skill Runner。
- Watchdog Worker。

Worker 之间通过队列、事件和持久化数据协作。

不要让 Agent Worker 直接访问宿主机 Docker Socket。

## 12.9 Execution Sandbox

所有不可信代码和 Skill 必须在隔离环境中运行。

开发阶段可以采用 Docker 容器。

生产阶段评估：
- 专用 Docker Daemon。
- gVisor。
- 更严格的容器运行时隔离。
- 文件系统与网络策略。

Agent 工具必须由受控服务提供，不能让模型直接连接数据库。

---

# 十三、项目目录结构

采用 Monorepo：

orgweave/

apps/
  web/
  api/

workers/
  agent-worker/
  temporal-worker/
  skill-runner/
  watchdog-worker/

packages/
  shared-types/
  agent-sdk/
  skill-sdk/

infra/
  docker/
  temporal/
  litellm/
  postgres/
  monitoring/

docs/
  IMPLEMENTATION_MASTER_PROMPT.md
  ARCHITECTURE.md
  DATABASE.md
  API.md
  SECURITY.md
  AGENT_RUNTIME.md
  TAKEOVER.md
  ROADMAP.md

scripts/

docker-compose.yml
.env.example
Makefile
README.md
.gitignore

可以在实际开发中调整，但必须保持模块职责清晰。

---

# 十四、API 设计

API 统一使用 /api/v1。

至少规划以下模块：

- auth
- tenants
- memberships
- departments
- members
- agents
- agent-sessions
- agent-runs
- agent-delegations
- agent-memories
- agent-tools
- agent-skills
- groups
- messages
- goals
- tasks
- automations
- artifacts
- takeovers
- interventions
- alerts
- audit
- models
- files

WebSocket 支持：

- 消息实时广播。
- Agent 状态。
- Session 事件。
- Task 进度。
- Delegation 状态。
- Watchdog 告警。
- Takeover 状态。

每个 WebSocket 连接、订阅和消息发送都必须进行身份与权限验证。

---

# 十五、审计与安全

必须建立完整的审计系统。

记录：

- 登录。
- 用户操作。
- 租户切换。
- 权限变更。
- Agent 创建和修改。
- Agent 工具调用。
- Agent 委派。
- Skill 安装。
- 数据访问。
- 管理员接管。
- 人工干预。
- 强制终止。
- 模型调用。
- 自动化执行。

审计事件至少包含：

- tenant_id
- actor_type
- actor_id
- action
- resource_type
- resource_id
- timestamp
- result
- metadata

重要安全要求：

1. 模型不能扩大自己的权限。
2. Agent 不能绕过 Task Contract。
3. 子 Agent 不能继承超出父任务的权限。
4. 不同租户数据必须严格隔离。
5. Agent 不直接连接数据库。
6. API 不暴露宿主机 Docker Socket。
7. 模型 Key 不写入 Prompt。
8. 工具调用必须二次授权。
9. 人工接管必须审计。
10. 高风险操作必须支持审批。

---

# 十六、开发阶段与验收标准

必须采用分阶段开发。

不要一次性生成整个系统。

每个阶段完成后运行测试、检查代码、更新文档，再进入下一阶段。

## Phase 0：项目基础设施

当前第一步只执行 Phase 0。

目标：

建立完整 Monorepo 和可启动开发环境。

完成：

1. 创建 Next.js 前端。
2. 创建 FastAPI 后端。
3. 创建 PostgreSQL + pgvector。
4. 创建 Redis。
5. 创建 Temporal 开发环境。
6. 创建 LiteLLM 配置。
7. 创建 MinIO。
8. 创建 Agent Worker 基础骨架。
9. 创建 Temporal Worker 基础骨架。
10. 创建 Skill Runner 基础骨架。
11. 创建 Watchdog Worker 基础骨架。
12. 创建 Alembic。
13. 创建统一环境变量配置。
14. 创建健康检查 API。
15. 创建 Docker Compose。
16. 创建 Makefile。
17. 创建 README。
18. 创建基础测试。
19. 创建基础 CI 配置。
20. 创建架构文档。

验收：

- docker compose config 成功。
- 所有基础服务能够启动。
- Web 前端能够打开。
- API 健康检查成功。
- PostgreSQL 能连接。
- pgvector 扩展可用。
- Redis 可连接。
- Temporal 可访问。
- LiteLLM 服务可访问。
- MinIO 可访问。
- Alembic 能执行基础迁移。
- pytest 通过。
- 前端基础检查通过。

本阶段不实现完整业务功能。

## Phase 1：组织与租户

完成：

- 用户认证。
- Tenant。
- TenantMembership。
- 部门。
- 成员。
- 人类成员。
- AI Member。
- 角色和权限。
- 租户隔离。
- RLS。
- 基础管理界面。

验收：

不同租户无法访问彼此数据。

## Phase 2：群聊与消息

完成：

- 单聊。
- 群聊。
- 成员管理。
- @成员。
- @AI 员工。
- WebSocket。
- 消息历史。
- 文件附件。
- 实时状态。

验收：

群聊正常工作，只有明确触发的 AI 员工才执行任务。

## Phase 3：Agent Runtime

完成：

- Agent 配置。
- Agent Session。
- Agent Run。
- 模型调用。
- Tool Calling。
- Context Manager。
- Memory。
- 执行限制。
- Agent 状态管理。

验收：

可以创建一个 AI 员工，让它接收任务并执行工具。

## Phase 4：Agent Delegation

完成：

- 员工调用员工。
- 独立 Child Session。
- 异步委派。
- 并行任务。
- 任务依赖。
- 结果回传。
- 任务取消。
- 委派权限。

验收：

CTO 能够调用 Researcher、Developer 和 QA，完成一个有实际交付物的任务。

## Phase 5：Skills 与工具生态

完成：

- Skill Registry。
- Skill Version。
- Agent Skill Installation。
- Skill Runner。
- MCP 集成。
- 权限控制。
- Skill 安全隔离。

验收：

不同 Agent 可以安装和使用不同 Skills，权限互不混淆。

## Phase 6：Goals & Tasks

完成：

- 目标管理。
- 任务拆解。
- 任务分配。
- 任务依赖。
- Task Contract。
- 审批。
- 交付物。
- 进度管理。

验收：

用户可以下达一个高层目标，由 AI 团队自主拆解和完成。

## Phase 7：Watchdog & Human Takeover

完成：

- Observe。
- Guide。
- Takeover。
- Kill。
- Agent Watchdog。
- 循环检测。
- 预算监控。
- 异常告警。
- Session Snapshot。
- 管理员工作现场。
- 审计日志。

验收：

管理员能够观察任意授权 Session，发现循环后暂停执行，并接管或终止任务。

## Phase 8：Automation

完成：

- Cron。
- Webhook。
- Event Trigger。
- Temporal 工作流。
- 定时任务。
- 自动通知。
- 执行历史。
- 幂等与重试。

验收：

AI 员工可以按照时间或事件自动启动任务。

---

# 十七、开发规范

你必须遵守以下开发原则：

1. 优先构建真正可运行的软件，而不是只输出设计文档。
2. 不允许用大量 Mock 代码冒充功能完成。
3. 每个阶段必须有真实测试。
4. 关键业务逻辑必须有类型定义。
5. 数据库结构必须通过 Alembic 迁移管理。
6. API 必须有 OpenAPI 文档。
7. 所有租户数据必须经过权限校验。
8. 所有 Agent 工具调用必须记录。
9. 所有后台任务必须支持状态持久化。
10. 所有关键操作必须可审计。
11. 不允许把密钥提交到 Git。
12. 不允许把不可信代码直接运行在 API 进程中。
13. 不允许让模型直接执行 SQL。
14. 不允许用 Prompt 替代权限系统。
15. 不允许把 Agent 身份与 Session 混为一谈。
16. 不允许通过简单修改数据库状态假装已经暂停 Worker。
17. 不允许跳过失败测试。
18. 不允许在没有解释的情况下随意更换核心技术栈。

代码应易于理解、模块化、便于后续扩展。

对于关键架构决策，记录在 docs/ARCHITECTURE.md。

遇到不确定的实现细节，优先采用简单、可测试、可维护的方案，并记录决策。

---

# 十八、当前执行指令：只做 Phase 0

现在开始执行 Phase 0。

不要尝试一次性实现全部产品。

请按以下顺序工作：

1. 检查当前项目目录。
2. 阅读本项目总指令。
3. 创建 Monorepo。
4. 创建前后端基础项目。
5. 创建 Docker Compose。
6. 创建基础 Worker。
7. 创建环境变量示例。
8. 创建数据库迁移基础。
9. 创建健康检查。
10. 启动并检查基础服务。
11. 执行测试。
12. 更新 README 和架构文档。

开始之前，先给出 Phase 0 的具体执行计划和预计创建的文件清单。

然后直接开始实施，不要只停留在计划阶段。

如果遇到需要真实 API Key 的服务，不要伪造 Key。应提供可配置的占位环境变量，并保证没有配置 Key 时基础设施仍然能够启动。

如果某个服务暂时无法启动，说明原因，提供可复现的错误和解决方法，不得宣称验收通过。

完成后给出：

- 项目目录结构。
- 已创建文件。
- 实际启动命令。
- 服务访问地址。
- 测试结果。
- 尚未完成的事项。
- Phase 1 的下一步计划。

**现在只执行 Phase 0。**