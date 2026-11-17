# Human Takeover 设计

> **实现状态：未实现。** Phase 0 不包含接管、暂停、终止或快照能力。本文固定后续控制语义，避免用“改数据库状态”冒充执行控制。

## 1. 控制模式

| 模式 | 行为 |
|---|---|
| Observe | 只读观察任务、步骤、模型/工具调用、token/费用、子 Agent、错误 |
| Guide | 注入指令、修正目标与约束、要求重新规划 |
| Takeover | 管理员取得 Session 控制权：暂停 AI 执行，禁止新模型请求、工具调用与新委派；可人工发消息、改计划、执行已授权工具、取消子任务、恢复 AI |
| Kill | 立即阻止新模型/工具调用，取消可取消任务，停止委派，记录不可撤销外部副作用，保存现场与审计 |

## 2. 执行控制要求

- 统一 Takeover Controller，不得仅在数据库写 `paused=true`。
- Agent Worker、Temporal Worker、Skill Runner 都必须支持执行控制：
  - 执行控制令牌（带版本/失效时间）；
  - 每次进入模型调用、工具调用、委派前校验 Session 状态；
  - 工具调用前二次授权，包括管理员手工调用；
  - 取消传播到子任务。
- 对外部操作必须记录：是否支持取消、是否已产生副作用、是否可回滚、取消结果。
- 释放控制权后，Agent 只能基于最新任务状态恢复，不能回放旧计划。

## 3. 人工操作标记

所有管理员操作写入审计，标记 `actor_type=human` 与 `human_action=true`，不得混同为 AI 自主执行。审计字段至少包含 `tenant_id`、`actor_type`、`actor_id`、`action`、`resource_type`、`resource_id`、`timestamp`、`result`、`metadata`。

## 4. 检查点

- 支持 Session Snapshot。
- 从历史检查点创建**新执行分支**，保留旧历史。
- 不假设外部副作用可撤销；分支只解决上下文/计划回退。

## 5. Phase 7 验收

管理员能观察任意授权 Session，发现循环后暂停执行，并成功接管或终止；审计完整，且没有新的模型/工具调用穿透暂停。

## 6. Phase 0 已有的可复用基础

- Worker 心跳与 Redis 告警频道 `orgweave:watchdog:alerts`。
- Redis 作为跨进程控制通道的基础。
- `/ws/v1` 已具备事件传输雏形（认证在 Phase 1 加入）。

这些仅为基础设施，不构成接管功能。
