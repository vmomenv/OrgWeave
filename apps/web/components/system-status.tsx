"use client";

import { useCallback, useEffect, useState } from "react";
import type {
  DependencyCheck,
  HealthSnapshot,
  ReadinessResponse,
} from "@orgweave/shared-types";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  RefreshCw,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");
const REFRESH_MS = 15_000;

const DEPENDENCY_LABELS: Record<string, string> = {
  postgres: "PostgreSQL + pgvector",
  redis: "Redis",
  minio: "MinIO",
  temporal: "Temporal",
  litellm: "LiteLLM",
};

const DEPENDENCY_ROLES: Record<string, string> = {
  postgres: "主数据库 / 向量检索",
  redis: "队列 / 心跳 / 缓存",
  minio: "对象存储",
  temporal: "工作流引擎",
  litellm: "模型网关",
};

function formatTime(iso: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(iso));
}

function StatusDot({ status }: { status: DependencyCheck["status"] }) {
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 rounded-full",
        status === "ok" ? "bg-success" : "bg-destructive",
      )}
      aria-hidden
    />
  );
}

function DependencyCard({ check }: { check: DependencyCheck }) {
  const ok = check.status === "ok";
  return (
    <Card>
      <CardHeader className="space-y-2 pb-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-medium">
            <StatusDot status={check.status} />
            {DEPENDENCY_LABELS[check.name] ?? check.name}
          </div>
          <Badge variant={ok ? "success" : "destructive"}>
            {ok ? "正常" : "异常"}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          {DEPENDENCY_ROLES[check.name] ?? "基础设施依赖"}
        </p>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="flex items-baseline justify-between text-xs text-muted-foreground">
          <span>响应延迟</span>
          <span className="font-mono text-foreground">
            {check.latency_ms.toFixed(1)} ms
          </span>
        </p>
        <p
          className="truncate font-mono text-[11px] text-muted-foreground"
          title={check.detail ?? ""}
        >
          {check.detail ?? "—"}
        </p>
      </CardContent>
    </Card>
  );
}

function OfflinePanel({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <Card className="border-destructive/40">
      <CardContent className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <AlertTriangle
            className="mt-0.5 h-5 w-5 shrink-0 text-destructive"
            aria-hidden
          />
          <div className="space-y-1">
            <p className="text-sm font-medium">无法获取 API 健康状态</p>
            <p className="break-all text-xs text-muted-foreground">{error}</p>
            <p className="text-xs text-muted-foreground">
              请确认已运行{" "}
              <code className="rounded bg-muted px-1 py-0.5 font-mono">
                make infra
              </code>{" "}
              和{" "}
              <code className="rounded bg-muted px-1 py-0.5 font-mono">
                make api
              </code>
              。
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="mr-2 h-3.5 w-3.5" aria-hidden />
          重试
        </Button>
      </CardContent>
    </Card>
  );
}

export function SystemStatus({ initial }: { initial: HealthSnapshot }) {
  const [snapshot, setSnapshot] = useState<HealthSnapshot>(initial);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    const checkedAt = new Date().toISOString();
    try {
      const response = await fetch(`${API_BASE}/api/v1/health/ready`, {
        cache: "no-store",
        signal: AbortSignal.timeout(4000),
      });
      const readiness = (await response.json()) as ReadinessResponse;
      setSnapshot((current) => ({
        ...current,
        readiness,
        error: null,
        checkedAt,
      }));
    } catch (error) {
      setSnapshot((current) => ({
        ...current,
        error:
          error instanceof Error ? error.message : "API 健康检查请求失败",
        checkedAt,
      }));
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      void refresh();
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const readiness = snapshot.readiness;
  const ready = readiness?.status === "ready";

  return (
    <section className="space-y-4" aria-labelledby="status-heading">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h2 id="status-heading" className="text-lg font-semibold tracking-tight">
            基础设施状态
          </h2>
          <p className="text-sm text-muted-foreground">
            实时探测数据库、缓存、存储、工作流与模型网关。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock className="h-3.5 w-3.5" aria-hidden />
            每 15 秒自动刷新 · {readiness ? formatTime(snapshot.checkedAt) : "—"} UTC
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refresh()}
            disabled={refreshing}
          >
            <RefreshCw
              className={cn("mr-2 h-3.5 w-3.5", refreshing && "animate-spin")}
              aria-hidden
            />
            刷新
          </Button>
        </div>
      </div>

      {snapshot.error ? (
        <OfflinePanel error={snapshot.error} onRetry={() => void refresh()} />
      ) : null}

      {readiness ? (
        <div
          className={cn(
            "flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3",
            ready
              ? "border-success/30 bg-success/5"
              : "border-warning/30 bg-warning/5",
          )}
          role="status"
        >
          {ready ? (
            <CheckCircle2 className="h-5 w-5 text-success" aria-hidden />
          ) : (
            <XCircle className="h-5 w-5 text-warning" aria-hidden />
          )}
          <div>
            <p className="text-sm font-medium">
              {ready ? "全部依赖在线，系统已就绪" : "部分依赖异常，系统降级运行"}
            </p>
            <p className="text-xs text-muted-foreground">
              5 项依赖中{" "}
              {readiness.checks.filter((check) => check.status === "ok").length} 项正常 ·
              API v{readiness.version}
            </p>
          </div>
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {readiness?.checks.map((check) => (
          <DependencyCard key={check.name} check={check} />
        ))}
      </div>
    </section>
  );
}
