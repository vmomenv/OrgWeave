import type { Metadata } from "next";
import {
  ArrowUpRight,
  CheckCircle2,
  CircleDashed,
  ExternalLink,
  FileJson,
  Network,
  Server,
  Workflow,
} from "lucide-react";

import { SystemStatus } from "@/components/system-status";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { getHealthSnapshot } from "@/lib/api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "系统控制台 — OrgWeave Phase 0",
};

const PUBLIC_API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

const SERVICE_LINKS = [
  {
    name: "API 文档",
    href: `${PUBLIC_API_BASE}/api/v1/docs`,
    detail: "Swagger UI · /api/v1",
    icon: Server,
  },
  {
    name: "OpenAPI Schema",
    href: `${PUBLIC_API_BASE}/api/v1/openapi.json`,
    detail: "机器可读接口契约",
    icon: FileJson,
  },
  {
    name: "Temporal UI",
    href: "http://localhost:8080",
    detail: "工作流执行与历史",
    icon: Workflow,
  },
  {
    name: "MinIO 控制台",
    href: "http://localhost:9001",
    detail: "对象存储（凭据见 .env）",
    icon: Network,
  },
];

const COMPLETED = [
  "Monorepo（pnpm + Python workspace）",
  "PostgreSQL 16 + pgvector",
  "Redis、Temporal、LiteLLM、MinIO",
  "FastAPI /api/v1 健康检查与 OpenAPI",
  "WebSocket /ws/v1 基础协议",
  "四类 Worker 骨架与心跳",
  "Alembic 基线迁移",
  "pytest 单元与集成测试",
];

const NEXT_PHASES = [
  { phase: "Phase 1", title: "组织与租户", detail: "用户认证、Tenant、RLS、成员与部门" },
  { phase: "Phase 2", title: "群聊与消息", detail: "群聊、@AI 员工、WebSocket 事件" },
  { phase: "Phase 3", title: "Agent Runtime", detail: "Session、Run、工具调用与记忆" },
  { phase: "Phase 4", title: "Agent 委派", detail: "子任务、异步执行、结果回传" },
];

export default async function HomePage() {
  const snapshot = await getHealthSnapshot();

  return (
    <main className="mx-auto max-w-6xl space-y-10 px-4 py-10 sm:px-6">
      <section className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">Phase 0</Badge>
          <Badge variant={snapshot.readiness?.status === "ready" ? "success" : "warning"}>
            {snapshot.readiness?.status === "ready" ? "基础设施就绪" : "等待依赖"}
          </Badge>
          <span className="text-xs text-muted-foreground">
            API v{snapshot.meta?.version ?? "0.1.0"} · 模块化单体 + 独立 Worker
          </span>
        </div>
        <div className="max-w-3xl space-y-3">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            AI 组织操作系统 · 开发控制台
          </h1>
          <p className="text-sm leading-6 text-muted-foreground sm:text-base">
            本阶段建立可运行的基础设施：多租户数据库、消息队列、工作流引擎、模型网关、
            对象存储，以及 API 与四类 Worker 的真实启动链路。业务模块尚未实现。
          </p>
        </div>
      </section>

      <SystemStatus initial={snapshot} />

      <section className="grid gap-4 lg:grid-cols-2" aria-label="Phase 0 详情">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ExternalLink className="h-4 w-4 text-muted-foreground" aria-hidden />
              服务入口
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {SERVICE_LINKS.map((link) => {
              const Icon = link.icon;
              return (
                <a
                  key={link.name}
                  href={link.href}
                  target="_blank"
                  rel="noreferrer"
                  className="group flex items-center justify-between gap-3 rounded-md px-2 py-2.5 transition-colors hover:bg-accent"
                >
                  <span className="flex items-center gap-3">
                    <Icon className="h-4 w-4 text-muted-foreground" aria-hidden />
                    <span className="space-y-0.5">
                      <span className="block text-sm font-medium">{link.name}</span>
                      <span className="block text-xs text-muted-foreground">
                        {link.detail}
                      </span>
                    </span>
                  </span>
                  <ArrowUpRight
                    className="h-3.5 w-3.5 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
                    aria-hidden
                  />
                </a>
              );
            })}
            <Separator className="my-2" />
            <div className="grid gap-2 px-2 py-1 text-xs sm:grid-cols-2">
              <div>
                <p className="text-muted-foreground">WebSocket</p>
                <p className="font-mono">ws://localhost:8000/ws/v1</p>
              </div>
              <div>
                <p className="text-muted-foreground">LiteLLM 网关</p>
                <p className="font-mono">http://localhost:4000</p>
              </div>
              <div>
                <p className="text-muted-foreground">Skill Runner</p>
                <p className="font-mono">http://localhost:8001/health/live</p>
              </div>
              <div>
                <p className="text-muted-foreground">Postgres / Redis</p>
                <p className="font-mono">localhost:5432 / 6379</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Phase 0 完成项</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2 sm:grid-cols-2">
              {COMPLETED.map((item) => (
                <div key={item} className="flex items-start gap-2 text-xs">
                  <CheckCircle2
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success"
                    aria-hidden
                  />
                  <span>{item}</span>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>后续阶段（规划中）</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {NEXT_PHASES.map((item) => (
                <div key={item.phase} className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-2">
                    <CircleDashed
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground"
                      aria-hidden
                    />
                    <div>
                      <p className="text-xs font-medium">
                        {item.phase} · {item.title}
                      </p>
                      <p className="text-xs text-muted-foreground">{item.detail}</p>
                    </div>
                  </div>
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    未实现
                  </span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="rounded-lg border bg-muted/30 p-5">
        <h2 className="text-sm font-semibold">本地验收命令</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          完整验证脚本会检查 Compose 配置、服务健康、数据库迁移、pytest 与前端构建。
        </p>
        <pre className="mt-3 overflow-x-auto rounded-md bg-background p-3 font-mono text-xs">
{`make bootstrap      # 安装依赖并启动基础设施
make migrate        # 应用 Alembic 迁移
ORGWEAVE_INTEGRATION=1 make test
make verify         # Phase 0 全量验收`}
        </pre>
      </section>
    </main>
  );
}
