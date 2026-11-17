"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  Bot,
  Brain,
  CircleStop,
  Plus,
  RefreshCw,
  Save,
  Send,
  Wrench,
  GitBranch,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiClientError } from "@/lib/api-client";
import type {
  Agent,
  AgentMemory,
  AgentRun,
  AgentSession,
  AgentToolCall,
  Delegation,
  SessionMessage,
} from "@/lib/api-client";
import { cn } from "@/lib/utils";

function errorMessage(error: unknown): string {
  if (error instanceof ApiClientError) return error.message;
  if (error instanceof Error) return error.message;
  return "操作失败";
}

const STATUS_LABELS: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  timeout: "超时",
  active: "活跃",
  paused: "暂停",
  killed: "已终止",
};

export function AgentPanel({
  tenantId,
  canManage,
}: {
  tenantId: string;
  canManage: boolean;
}) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [memories, setMemories] = useState<AgentMemory[]>([]);
  const [input, setInput] = useState("");
  const [run, setRun] = useState<AgentRun | null>(null);
  const [tools, setTools] = useState<AgentToolCall[]>([]);
  const [delegations, setDelegations] = useState<Delegation[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<Partial<Agent>>({});
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const agent = agents.find((item) => item.id === agentId) ?? null;
  const session = sessions.find((item) => item.id === sessionId) ?? null;

  const loadAgents = useCallback(async (): Promise<Agent[]> => {
    const data = await api.get<Agent[]>("agents", tenantId);
    setAgents(data);
    return data;
  }, [tenantId]);

  const loadSessions = useCallback(
    async (id: string): Promise<AgentSession[]> => {
      const data = await api.get<AgentSession[]>(`agents/${id}/sessions`, tenantId);
      setSessions(data);
      return data;
    },
    [tenantId],
  );

  const loadMemories = useCallback(
    async (id: string) => {
      const data = await api.get<AgentMemory[]>(`agents/${id}/memories`, tenantId);
      setMemories(data);
    },
    [tenantId],
  );

  const loadMessages = useCallback(
    async (id: string) => {
      const data = await api.get<SessionMessage[]>(`sessions/${id}/messages`, tenantId);
      setMessages(data);
    },
    [tenantId],
  );

  const loadDelegations = useCallback(
    async (id: string) => {
      const data = await api.get<Delegation[]>(
        `sessions/${id}/delegations`,
        tenantId,
      );
      setDelegations(data);
    },
    [tenantId],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await loadAgents();
        if (!cancelled) {
          setAgentId((current) => current ?? data[0]?.id ?? null);
        }
      } catch (loadError) {
        if (!cancelled) setError(errorMessage(loadError));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadAgents]);

  useEffect(() => {
    if (!agentId) return;
    const current = agents.find((item) => item.id === agentId);
    if (current) {
      setConfig({
        system_prompt: current.system_prompt,
        model_alias: current.model_alias,
        max_steps: current.max_steps,
        token_budget: current.token_budget,
        max_tool_calls: current.max_tool_calls,
      });
    }
    let cancelled = false;
    (async () => {
      try {
        const [sessionList] = await Promise.all([
          loadSessions(agentId),
          loadMemories(agentId),
        ]);
        if (!cancelled) {
          setSessionId((value) =>
            sessionList.some((item) => item.id === value)
              ? value
              : (sessionList[0]?.id ?? null),
          );
        }
      } catch (loadError) {
        if (!cancelled) setError(errorMessage(loadError));
      }
    })();
    return () => {
      cancelled = true;
    };
    // agents intentionally not in deps to avoid loop after config refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, loadSessions, loadMemories]);

  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      setRun(null);
      setTools([]);
      setDelegations([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        await Promise.all([loadMessages(sessionId), loadDelegations(sessionId)]);
      } catch (loadError) {
        if (!cancelled) setError(errorMessage(loadError));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, loadMessages, loadDelegations]);

  useEffect(() => {
    if (!run || !["queued", "running"].includes(run.status)) {
      if (pollTimer.current) clearInterval(pollTimer.current);
      return;
    }
    pollTimer.current = setInterval(async () => {
      try {
        const updated = await api.get<AgentRun>(`runs/${run.id}`, tenantId);
        setRun(updated);
        if (!["queued", "running"].includes(updated.status)) {
          if (pollTimer.current) clearInterval(pollTimer.current);
          if (sessionId) {
            await loadMessages(sessionId);
            await loadDelegations(sessionId);
            if (agentId) await loadMemories(agentId);
          }
          const toolList = await api.get<AgentToolCall[]>(
            `runs/${updated.id}/tools`,
            tenantId,
          );
          setTools(toolList);
        }
      } catch (pollError) {
        setError(errorMessage(pollError));
      }
    }, 1500);
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, [run, tenantId, sessionId, agentId, loadMessages, loadMemories, loadDelegations]);

  async function createSession() {
    if (!agentId) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.post<AgentSession>(
        `agents/${agentId}/sessions`,
        { title: `任务会话 ${new Date().toLocaleString("zh-CN")}` },
        tenantId,
      );
      await loadSessions(agentId);
      setSessionId(created.id);
    } catch (createError) {
      setError(errorMessage(createError));
    } finally {
      setBusy(false);
    }
  }

  async function saveConfig(event: FormEvent) {
    event.preventDefault();
    if (!agentId) return;
    setBusy(true);
    setError(null);
    try {
      await api.patch(`agents/${agentId}`, config, tenantId);
      await loadAgents();
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setBusy(false);
    }
  }

  async function submitRun(event: FormEvent) {
    event.preventDefault();
    if (!sessionId || !input.trim()) return;
    setBusy(true);
    setError(null);
    setTools([]);
    try {
      const created = await api.post<AgentRun>(
        `sessions/${sessionId}/runs`,
        { input: input.trim() },
        tenantId,
      );
      setRun(created);
      setInput("");
      await loadMessages(sessionId);
      await loadSessions(agentId ?? "");
    } catch (runError) {
      setError(errorMessage(runError));
    } finally {
      setBusy(false);
    }
  }

  async function cancelRun() {
    if (!run) return;
    setBusy(true);
    try {
      const updated = await api.post<AgentRun>(
        `runs/${run.id}/cancel`,
        undefined,
        tenantId,
      );
      setRun(updated);
    } catch (cancelError) {
      setError(errorMessage(cancelError));
    } finally {
      setBusy(false);
    }
  }

  if (agents.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <Bot className="h-4 w-4" aria-hidden />
            AI 员工
          </CardTitle>
          <CardDescription>
            尚未创建 AI 员工。请先在“成员”页创建 AI 成员，系统会自动生成 Agent 配置。
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Select
            value={agentId ?? ""}
            onChange={(event) => {
              setAgentId(event.target.value);
              setSessionId(null);
              setRun(null);
            }}
            className="w-56"
            aria-label="选择 AI 员工"
          >
            {agents.map((item) => (
              <option key={item.id} value={item.id}>
                {item.member_name} {item.member_title ? `· ${item.member_title}` : ""}
              </option>
            ))}
          </Select>
          <Badge variant={agent?.member_ai_enabled ? "success" : "outline"}>
            AI {agent?.member_ai_enabled ? "已启用" : "已关闭"}
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => void createSession()}>
            <Plus className="mr-1.5 h-3.5 w-3.5" aria-hidden />
            新建会话
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              void loadAgents();
              if (agentId) {
                void loadSessions(agentId);
                void loadMemories(agentId);
              }
            }}
          >
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" aria-hidden />
            刷新
          </Button>
        </div>
      </div>

      {error ? <p className="text-xs text-destructive">{error}</p> : null}

      <div className="grid gap-3 xl:grid-cols-[1fr_320px]">
        <div className="space-y-3">
          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0 border-b px-4 py-2.5">
              <div>
                <CardTitle className="text-sm">
                  {session?.title ?? "选择或新建会话"}
                </CardTitle>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {session
                    ? `${STATUS_LABELS[session.status] ?? session.status} · 控制模式 ${session.control_mode} · ${session.token_usage} tokens`
                    : `${sessions.length} 个独立 Session`}
                </p>
              </div>
              <Select
                value={sessionId ?? ""}
                onChange={(event) => setSessionId(event.target.value)}
                className="h-8 w-44 text-xs"
                disabled={sessions.length === 0}
                aria-label="选择会话"
              >
                {sessions.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                    {item.last_run_status
                      ? ` · ${STATUS_LABELS[item.last_run_status] ?? item.last_run_status}`
                      : ""}
                  </option>
                ))}
              </Select>
            </CardHeader>
            <CardContent className="max-h-[380px] space-y-3 overflow-y-auto p-4">
              {messages.length === 0 ? (
                <p className="py-10 text-center text-xs text-muted-foreground">
                  会话为空。输入任务，由该 AI 员工在独立 Session 中执行。
                </p>
              ) : null}
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={cn(
                    "rounded-md border p-2.5",
                    message.role === "assistant"
                      ? "bg-muted/30"
                      : message.role === "tool"
                        ? "border-dashed"
                        : "",
                  )}
                >
                  <div className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                    <span className="font-medium">
                      {message.role === "assistant"
                        ? agent?.member_name ?? "assistant"
                        : message.role === "tool"
                          ? "工具结果"
                          : "用户"}
                    </span>
                    {message.tool_call_id ? (
                      <span className="font-mono">{message.tool_call_id.slice(0, 12)}</span>
                    ) : null}
                  </div>
                  <p className="whitespace-pre-wrap break-words text-sm">
                    {message.content || "（无文本内容）"}
                  </p>
                </div>
              ))}
            </CardContent>
            <div className="border-t p-3">
              <form onSubmit={submitRun} className="flex items-end gap-2">
                <Textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder="给 AI 员工下达任务…"
                  className="min-h-[44px] flex-1 resize-none"
                />
                <Button
                  type="submit"
                  size="icon"
                  disabled={busy || !sessionId || !input.trim()}
                  aria-label="执行任务"
                >
                  <Send className="h-4 w-4" aria-hidden />
                </Button>
              </form>
              {run ? (
                <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                  <Badge
                    variant={
                      run.status === "completed"
                        ? "success"
                        : run.status === "failed"
                          ? "destructive"
                          : "warning"
                    }
                  >
                    {STATUS_LABELS[run.status] ?? run.status}
                  </Badge>
                  <span>
                    steps {run.steps} · tools {run.tool_calls_count} · tokens{" "}
                    {run.token_usage}
                  </span>
                  {["queued", "running"].includes(run.status) ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => void cancelRun()}
                      disabled={busy}
                    >
                      <CircleStop className="mr-1 h-3 w-3" aria-hidden />
                      取消执行
                    </Button>
                  ) : null}
                  {run.error ? (
                    <span className="text-destructive">{run.error}</span>
                  ) : null}
                </div>
              ) : null}
              {run?.output ? (
                <div className="mt-2 rounded-md border border-success/30 bg-success/5 p-2 text-xs">
                  <p className="mb-1 font-medium text-success">最终交付</p>
                  <p className="whitespace-pre-wrap">{run.output}</p>
                </div>
              ) : null}
            </div>
          </Card>

          {delegations.length > 0 ? (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-xs">
                  <GitBranch className="h-3.5 w-3.5" aria-hidden />
                  委派任务 · {delegations.length}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {delegations.map((delegation) => {
                  const target = agents.find(
                    (item) => item.id === delegation.child_agent_id,
                  );
                  return (
                    <div key={delegation.id} className="rounded border p-2 text-[11px]">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium">
                          {target?.member_name ?? delegation.child_agent_id.slice(0, 8)}
                        </span>
                        <Badge
                          variant={
                            delegation.status === "completed"
                              ? "success"
                              : delegation.status === "failed"
                                ? "destructive"
                                : "warning"
                          }
                        >
                          {STATUS_LABELS[delegation.status] ?? delegation.status}
                        </Badge>
                      </div>
                      <p className="mt-0.5 line-clamp-2 text-muted-foreground">
                        {delegation.task}
                      </p>
                      {delegation.summary ? (
                        <p className="mt-1 line-clamp-3">{delegation.summary}</p>
                      ) : null}
                      <p className="mt-1 font-mono text-[9px] text-muted-foreground">
                        child session {delegation.child_session_id.slice(0, 8)}
                      </p>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          ) : null}

          {tools.length > 0 ? (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-xs">
                  <Wrench className="h-3.5 w-3.5" aria-hidden />
                  工具调用记录
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {tools.map((tool) => (
                  <div key={tool.id} className="rounded border p-2 text-[11px]">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono">{tool.tool_name}</span>
                      <Badge
                        variant={tool.status === "completed" ? "success" : "destructive"}
                      >
                        {tool.status}
                      </Badge>
                    </div>
                    <p className="mt-1 truncate text-muted-foreground">
                      参数 {JSON.stringify(tool.arguments)}
                    </p>
                    <p className="truncate text-muted-foreground">
                      结果 {JSON.stringify(tool.result)}
                    </p>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </div>

        <div className="space-y-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Agent 配置</CardTitle>
              <CardDescription className="text-[11px]">
                {agent?.member_name} · 硬限制由服务端与 Worker 共同执行
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={saveConfig} className="space-y-2.5">
                <div className="space-y-1">
                  <Label htmlFor="agent-model">模型别名</Label>
                  <Input
                    id="agent-model"
                    value={config.model_alias ?? ""}
                    onChange={(event) =>
                      setConfig((current) => ({ ...current, model_alias: event.target.value }))
                    }
                    disabled={!canManage}
                    maxLength={120}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="agent-prompt">System Prompt</Label>
                  <Textarea
                    id="agent-prompt"
                    value={config.system_prompt ?? ""}
                    onChange={(event) =>
                      setConfig((current) => ({ ...current, system_prompt: event.target.value }))
                    }
                    disabled={!canManage}
                    className="min-h-[80px] text-xs"
                    maxLength={8000}
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div className="space-y-1">
                    <Label htmlFor="agent-steps">最大步数</Label>
                    <Input
                      id="agent-steps"
                      type="number"
                      min={1}
                      max={100}
                      value={config.max_steps ?? 8}
                      onChange={(event) =>
                        setConfig((current) => ({
                          ...current,
                          max_steps: Number(event.target.value),
                        }))
                      }
                      disabled={!canManage}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="agent-tokens">Token 预算</Label>
                    <Input
                      id="agent-tokens"
                      type="number"
                      min={100}
                      value={config.token_budget ?? 50000}
                      onChange={(event) =>
                        setConfig((current) => ({
                          ...current,
                          token_budget: Number(event.target.value),
                        }))
                      }
                      disabled={!canManage}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="agent-tools">工具上限</Label>
                    <Input
                      id="agent-tools"
                      type="number"
                      min={0}
                      max={200}
                      value={config.max_tool_calls ?? 20}
                      onChange={(event) =>
                        setConfig((current) => ({
                          ...current,
                          max_tool_calls: Number(event.target.value),
                        }))
                      }
                      disabled={!canManage}
                    />
                  </div>
                </div>
                <div className="flex flex-wrap gap-1">
                  {(agent?.allowed_tools ?? []).map((tool) => (
                    <span
                      key={tool}
                      className="rounded border bg-muted/40 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                    >
                      {tool}
                    </span>
                  ))}
                </div>
                <Button type="submit" size="sm" disabled={!canManage || busy}>
                  <Save className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                  保存配置
                </Button>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-xs">
                <Brain className="h-3.5 w-3.5" aria-hidden />
                长期记忆
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {memories.length === 0 ? (
                <p className="text-[11px] text-muted-foreground">暂无记忆。</p>
              ) : null}
              {memories.slice(0, 8).map((memory) => (
                <div key={memory.id} className="rounded border p-2 text-[11px]">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-muted-foreground">
                      {memory.memory_type}
                    </span>
                    <span className="text-muted-foreground">
                      importance {memory.importance}
                    </span>
                  </div>
                  <p className="mt-0.5 line-clamp-3">{memory.content}</p>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-xs">会话列表</CardTitle>
            </CardHeader>
            <CardContent className="max-h-48 space-y-1 overflow-y-auto">
              {sessions.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setSessionId(item.id);
                    setRun(null);
                    setTools([]);
                  }}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-[11px] transition-colors",
                    sessionId === item.id ? "bg-accent" : "hover:bg-accent/60",
                  )}
                >
                  <span className="truncate">{item.title}</span>
                  <Badge variant="outline" className="shrink-0 text-[9px]">
                    {STATUS_LABELS[item.last_run_status ?? item.status] ??
                      item.last_run_status ??
                      item.status}
                  </Badge>
                </button>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
