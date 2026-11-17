# API 设计（Phase 0）

- REST 基址：`/api/v1`
- WebSocket：`/ws/v1`
- OpenAPI：`http://localhost:8000/api/v1/openapi.json`
- Swagger UI：`http://localhost:8000/api/v1/docs`
- 所有响应带 `x-request-id`（未提供则生成）。

## 1. 健康检查

### `GET /api/v1/health/live`

仅证明 API 进程可响应，不访问数据库或外部服务。

```json
{
  "status": "ok",
  "service": "orgweave-api",
  "version": "0.1.0",
  "timestamp": "2026-11-17T02:02:00Z"
}
```

### `GET /api/v1/health/ready`

并行探测 PostgreSQL（含 pgvector）、Redis、MinIO、Temporal、LiteLLM。

- 全部正常：HTTP 200，`status: "ready"`。
- 任一异常：HTTP 503，`status: "degraded"`；**仍返回完整逐项结果**，便于定位。
- 每项包含 `name`、`status`、`latency_ms`、`detail`；失败详情已脱敏（URL 中用户信息被替换）。

```json
{
  "status": "ready",
  "version": "0.1.0",
  "timestamp": "2026-11-17T02:02:00Z",
  "checks": [
    { "name": "postgres", "status": "ok", "latency_ms": 376.0, "detail": "database=orgweave pg=16.16 pgvector=0.8.7" },
    { "name": "redis", "status": "ok", "latency_ms": 355.0, "detail": "ping=ok" },
    { "name": "minio", "status": "ok", "latency_ms": 351.0, "detail": "bucket=orgweave present=true" },
    { "name": "temporal", "status": "ok", "latency_ms": 73.0, "detail": "host=localhost:7233 server=1.29.7" },
    { "name": "litellm", "status": "ok", "latency_ms": 45.0, "detail": "http=200" }
  ]
}
```

## 2. 元数据

### `GET /api/v1/meta`

```json
{
  "name": "OrgWeave",
  "api_version": "v1",
  "phase": "0",
  "version": "0.1.0",
  "api_prefix": "/api/v1",
  "ws_prefix": "/ws/v1",
  "openapi_url": "/api/v1/openapi.json",
  "docs_url": "/api/v1/docs"
}
```

## 3. WebSocket 协议

连接：`ws://localhost:8000/ws/v1`。

服务端先发送：

```json
{ "type": "hello", "timestamp": "...", "service": "orgweave-api", "version": "0.1.0", "api": "v1" }
```

客户端可发送：

```json
{ "type": "ping" }
{ "type": "server.info" }
```

服务端返回 `pong` 或 `server.info`。非法 JSON / 未知类型返回 `{"type":"error","reason":...}`。单帧上限 8 KiB，超限以关闭码 1009 断开。

**边界：** Phase 0 的 WebSocket 不传输任何租户、消息或 Agent 数据。Phase 1 引入认证后，每条连接与订阅都必须校验身份、租户与权限。

## 4. 错误与版本

- 业务错误未来统一为 `{ "error": { "code", "message", "details", "request_id" } }`；Phase 0 仅健康与元数据端点，暂无业务错误体。
- 破坏性变更必须升级 API 版本（`/api/v2`），不在 `/api/v1` 内改变既有字段语义。
- 数据库与外部依赖不可用时，readiness 必须返回 503 而非 200，供编排器摘除流量。

## 5. Phase 1 已实现端点

### 认证

- `POST /api/v1/auth/register`、`POST /auth/login`、`POST /auth/refresh`、`POST /auth/logout`
- `GET /auth/me`

### 租户与组织

- `GET/POST /api/v1/tenants`、`GET /tenants/{id}`
- `GET/PATCH /tenant`（需 `X-Tenant-ID`）
- `GET/POST /departments`、`PATCH/DELETE /departments/{id}`
- `GET/POST /members`、`GET/PATCH /members/{id}`、`PUT /members/{id}/roles`
- `GET /roles`、`GET /permissions`
- `GET /invitations`、`POST /invitations`、`POST /invitations/accept`、`DELETE /invitations/{id}`
- `GET /audit`

除认证与租户外，租户端点都必须携带 `X-Tenant-ID`。服务端会校验成员关系并设置
`app.tenant_id`；错误格式为 `{"error":{"code","message","details?"}}`。

### WebSocket 认证

`ws://localhost:8000/ws/v1?token=<access_token>`。缺少或无效 Token 会收到
`{"type":"error","reason":"unauthorized"}` 并以 4401 关闭。

## 6. Phase 2 已实现端点

- `GET/POST /groups`、`GET/PATCH /groups/{id}`
- `POST /groups/{id}/members`、`DELETE /groups/{id}/members/{member_id}`
- `GET/POST /groups/{id}/messages`（支持 `limit`、`search`）
- `POST /groups/{id}/read`
- `POST /groups/{id}/attachments`（multipart，10 MiB 限制）
- `GET /attachments/{id}`（流式下载，需群成员权限）

WebSocket：`ws://localhost:8000/ws/v1?token=<access>&tenant_id=<tenant>`。
连接时验证租户成员身份并返回该成员所在群；消息事件
`{"type":"message.created","group_id","message","mentioned_ai_ids"}` 仅转发给群成员。
客户端可发送 `{"type":"resubscribe"}` 刷新群订阅。

## 7. Phase 3 已实现端点

- `GET/POST /agents`、`GET/PATCH /agents/{id}`
- `GET/POST /agents/{id}/sessions`
- `GET /sessions/{id}`、`GET /sessions/{id}/messages`
- `POST /sessions/{id}/runs`（入队 Agent Worker；返回 Run）
- `GET /runs/{id}`、`GET /runs/{id}/tools`、`POST /runs/{id}/cancel`
- `GET/POST /agents/{id}/memories`

Run 的限制（max_steps、max_duration、token_budget、max_tool_calls、
max_consecutive_failures）由服务端存储并由 Worker 执行，模型无法扩大。
错误统一返回 `{"error":{"code","message"}}`。

## 8. 后续模块

Phase 1–8 将依次增加 `auth`、`tenants`、`memberships`、`departments`、`members`、`agents`、`agent-sessions`、`agent-runs`、`agent-delegations`、`agent-memories`、`agent-tools`、`agent-skills`、`groups`、`messages`、`goals`、`tasks`、`automations`、`artifacts`、`takeovers`、`interventions`、`alerts`、`audit`、`models`、`files`。每增加一个模块，必须同时提供 OpenAPI、权限检查与审计。
