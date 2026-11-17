"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  Building2,
  Check,
  ClipboardCopy,
  Layers,
  Loader2,
  LogOut,
  MessageSquare,
  Bot,
  Plus,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  Sparkles,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";

import { ThemeToggle } from "@/components/theme-toggle";
import { AgentPanel } from "@/components/workspace/agent-panel";
import { ChatPanel } from "@/components/workspace/chat-panel";
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
import { api, ApiClientError } from "@/lib/api-client";
import type {
  AuditLog,
  Department,
  Invitation,
  InvitationCreated,
  MeResponse,
  Member,
  Role,
  TenantContext,
} from "@/lib/api-client";
import { cn } from "@/lib/utils";

type Tab = "overview" | "chat" | "agents" | "members" | "departments" | "audit";

const TABS: { id: Tab; label: string; icon: typeof Activity }[] = [
  { id: "overview", label: "概览", icon: Activity },
  { id: "chat", label: "群聊", icon: MessageSquare },
  { id: "agents", label: "AI 员工", icon: Bot },
  { id: "members", label: "成员", icon: Users },
  { id: "departments", label: "部门", icon: Layers },
  { id: "audit", label: "审计", icon: ScrollText },
];

const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  member: "Member",
};

function errorMessage(error: unknown): string {
  if (error instanceof ApiClientError) return error.message;
  if (error instanceof Error) return error.message;
  return "操作失败";
}

function formatTime(iso: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

export function Workspace() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [context, setContext] = useState<TenantContext | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [audit, setAudit] = useState<AuditLog[]>([]);
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [issuedInvite, setIssuedInvite] = useState<InvitationCreated | null>(null);

  const loadMe = useCallback(async (): Promise<MeResponse | null> => {
    const response = await fetch("/api/auth/me", { cache: "no-store" });
    if (response.status === 401) {
      window.location.assign("/login");
      return null;
    }
    if (!response.ok) {
      throw new Error("无法加载账号信息");
    }
    const data = (await response.json()) as MeResponse;
    setMe(data);
    return data;
  }, []);

  const loadTenantData = useCallback(async (id: string) => {
    const [ctx, deps, mems, roleList, invites, logs] = await Promise.all([
      api.get<TenantContext>("tenant", id),
      api.get<Department[]>("departments", id),
      api.get<Member[]>("members", id),
      api.get<Role[]>("roles", id),
      api.get<Invitation[]>("invitations", id),
      api.get<AuditLog[]>("audit?limit=80", id),
    ]);
    setContext(ctx);
    setDepartments(deps);
    setMembers(mems);
    setRoles(roleList);
    setInvitations(invites);
    setAudit(logs);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await loadMe();
        if (!data || cancelled) return;
        const stored = localStorage.getItem("ow_tenant");
        const candidate = data.tenants.find((tenant) => tenant.id === stored);
        setTenantId(candidate?.id ?? data.tenants[0]?.id ?? null);
      } catch (loadError) {
        setError(errorMessage(loadError));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadMe]);

  useEffect(() => {
    if (!tenantId) {
      setContext(null);
      setDepartments([]);
      setMembers([]);
      setRoles([]);
      setInvitations([]);
      setAudit([]);
      return;
    }
    let cancelled = false;
    setBusy(true);
    setError(null);
    (async () => {
      try {
        await loadTenantData(tenantId);
        if (!cancelled) localStorage.setItem("ow_tenant", tenantId);
      } catch (loadError) {
        if (!cancelled) setError(errorMessage(loadError));
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenantId, loadTenantData]);

  async function refreshAll() {
    try {
      if (tenantId) await loadTenantData(tenantId);
      await loadMe();
    } catch (refreshError) {
      setError(errorMessage(refreshError));
    }
  }

  async function createTenant(name: string) {
    const tenant = await api.post<{ id: string }>("tenants", { name });
    const data = await loadMe();
    setTenantId(tenant.id);
    if (data) {
      setNotice(`已创建租户「${name}」`);
    }
  }

  async function acceptInvitation(token: string) {
    const result = await api.post<{ tenant_id: string; tenant_name: string | null }>(
      "invitations/accept",
      { token },
    );
    await loadMe();
    setTenantId(result.tenant_id);
    setNotice(`已加入「${result.tenant_name ?? "租户"}」`);
  }

  async function createDepartment(name: string, parentId: string | null) {
    if (!tenantId) return;
    await api.post("departments", { name, parent_id: parentId || null }, tenantId);
    await refreshAll();
    setNotice("部门已创建");
  }

  async function deleteDepartment(id: string) {
    if (!tenantId) return;
    try {
      await api.del(`departments/${id}`, tenantId);
      await refreshAll();
      setNotice("部门已删除");
    } catch (deleteError) {
      setError(errorMessage(deleteError));
    }
  }

  async function createAiMember(input: {
    name: string;
    title: string;
    departmentId: string;
    roleKey: string;
  }) {
    if (!tenantId) return;
    await api.post(
      "members",
      {
        member_type: "ai",
        display_name: input.name,
        title: input.title || null,
        department_id: input.departmentId || null,
        role_keys: [input.roleKey],
        ai_enabled: true,
      },
      tenantId,
    );
    await refreshAll();
    setNotice("AI 员工已创建");
  }

  async function updateMember(id: string, payload: Record<string, unknown>) {
    if (!tenantId) return;
    try {
      await api.patch(`members/${id}`, payload, tenantId);
      await refreshAll();
    } catch (updateError) {
      setError(errorMessage(updateError));
    }
  }

  async function setMemberRole(id: string, roleKey: string) {
    if (!tenantId) return;
    try {
      await api.put(`members/${id}/roles`, { role_keys: [roleKey] }, tenantId);
      await refreshAll();
      setNotice("角色已更新");
    } catch (roleError) {
      setError(errorMessage(roleError));
    }
  }

  async function inviteMember(email: string, roleKey: string) {
    if (!tenantId) return;
    const invitation = await api.post<InvitationCreated>(
      "invitations",
      { email, role_key: roleKey },
      tenantId,
    );
    setIssuedInvite(invitation);
    await refreshAll();
  }

  async function revokeInvitation(id: string) {
    if (!tenantId) return;
    try {
      await api.del(`invitations/${id}`, tenantId);
      await refreshAll();
    } catch (revokeError) {
      setError(errorMessage(revokeError));
    }
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.assign("/login");
  }

  const departmentName = useMemo(() => {
    const map = new Map(departments.map((department) => [department.id, department.name]));
    return (id: string | null) => (id ? (map.get(id) ?? "未知部门") : "未分组");
  }, [departments]);

  const canManageMembers = context?.permissions.includes("member.manage") ?? false;
  const canManageDepartments = context?.permissions.includes("department.manage") ?? false;
  const canInvite = context?.permissions.includes("invitation.manage") ?? false;
  const canReadAudit = context?.permissions.includes("audit.read") ?? false;

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden />
      </div>
    );
  }

  if (!me) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16">
        <Card>
          <CardContent className="space-y-3 p-6">
            <p className="text-sm font-medium">无法加载工作空间</p>
            <p className="text-xs text-muted-foreground">{error ?? "请重新登录"}</p>
            <Button onClick={() => window.location.assign("/login")}>返回登录</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Select
            aria-label="选择租户"
            value={tenantId ?? ""}
            onChange={(event) => {
              setTenantId(event.target.value || null);
              setNotice(null);
            }}
            className="w-56"
            disabled={me.tenants.length === 0}
          >
            {me.tenants.length === 0 ? <option value="">暂无租户</option> : null}
            {me.tenants.map((tenant) => (
              <option key={tenant.id} value={tenant.id}>
                {tenant.name} · {tenant.role_keys.join(", ")}
              </option>
            ))}
          </Select>
          {context ? (
            <Badge variant="success" className="hidden sm:inline-flex">
              {context.membership_status === "active" ? "已进入租户" : context.membership_status}
            </Badge>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/status"
            className="hidden text-xs text-muted-foreground hover:text-foreground sm:block"
          >
            系统状态
          </Link>
          <ThemeToggle />
          <span className="hidden text-xs text-muted-foreground md:block">
            {me.user.display_name} · {me.user.email}
          </span>
          <Button variant="outline" size="sm" onClick={() => void logout()}>
            <LogOut className="mr-2 h-3.5 w-3.5" aria-hidden />
            退出
          </Button>
        </div>
      </div>

      {error ? (
        <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="mt-4 flex items-center gap-2 rounded-md border border-success/30 bg-success/5 px-3 py-2 text-xs text-success">
          <Check className="h-3.5 w-3.5" aria-hidden />
          {notice}
        </div>
      ) : null}

      {me.tenants.length === 0 || !tenantId ? (
        <div className="mt-8 grid gap-4 lg:grid-cols-2">
          <CreateTenantCard onCreate={createTenant} />
          <AcceptInvitationCard onAccept={acceptInvitation} />
        </div>
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-[200px_1fr]">
          <aside className="space-y-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">{context?.name ?? "租户"}</CardTitle>
                <CardDescription className="text-[11px]">
                  {context?.role_keys.map((role) => ROLE_LABELS[role] ?? role).join(" · ")}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-1 p-3 pt-0">
                {TABS.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setTab(item.id)}
                      className={cn(
                        "flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm transition-colors",
                        tab === item.id
                          ? "bg-accent font-medium text-accent-foreground"
                          : "text-muted-foreground hover:bg-accent/60",
                      )}
                    >
                      <Icon className="h-4 w-4" aria-hidden />
                      {item.label}
                    </button>
                  );
                })}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs">当前权限</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-1 p-3 pt-0">
                {(context?.permissions ?? []).map((permission) => (
                  <span
                    key={permission}
                    className="rounded border bg-muted/40 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                  >
                    {permission}
                  </span>
                ))}
              </CardContent>
            </Card>

            <Button variant="outline" size="sm" className="w-full" onClick={() => void refreshAll()}>
              <RefreshCw className="mr-2 h-3.5 w-3.5" aria-hidden />
              刷新数据
            </Button>
          </aside>

          <section className="min-w-0 space-y-4">
            {busy ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                加载租户数据…
              </div>
            ) : null}

            {tab === "overview" && context ? (
              <Overview
                context={context}
                memberCount={members.length}
                aiCount={members.filter((member) => member.member_type === "ai").length}
                departmentCount={departments.length}
                auditCount={audit.length}
                invitationCount={invitations.filter((item) => item.status === "pending").length}
              />
            ) : null}

            {tab === "chat" && context ? (
              <ChatPanel
                key={tenantId}
                tenantId={context.id}
                currentMemberId={context.member_id}
                members={members}
                canManage={canManageMembers}
              />
            ) : null}

            {tab === "agents" && context ? (
              <AgentPanel
                key={tenantId}
                tenantId={context.id}
                canManage={canManageMembers}
              />
            ) : null}

            {tab === "members" ? (
              <MembersPanel
                members={members}
                departments={departments}
                roles={roles}
                invitations={invitations}
                issuedInvite={issuedInvite}
                canManage={canManageMembers}
                canInvite={canInvite}
                departmentName={departmentName}
                onCreateAi={createAiMember}
                onUpdate={updateMember}
                onSetRole={setMemberRole}
                onInvite={inviteMember}
                onRevokeInvitation={revokeInvitation}
                onClearInvite={() => setIssuedInvite(null)}
              />
            ) : null}

            {tab === "departments" ? (
              <DepartmentsPanel
                departments={departments}
                canManage={canManageDepartments}
                onCreate={createDepartment}
                onDelete={deleteDepartment}
              />
            ) : null}

            {tab === "audit" ? (
              <AuditPanel logs={audit} canRead={canReadAudit} />
            ) : null}
          </section>
        </div>
      )}
    </div>
  );
}

function CreateTenantCard({ onCreate }: { onCreate: (name: string) => Promise<void> }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onCreate(name);
      setName("");
    } catch (submitError) {
      setError(errorMessage(submitError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Building2 className="h-4 w-4 text-muted-foreground" aria-hidden />
          创建企业租户
        </CardTitle>
        <CardDescription>
          你将成为该租户的 Owner，并自动获得组织成员身份。
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="tenant-name">企业名称</Label>
            <Input
              id="tenant-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="例如：星火科技有限公司"
              minLength={2}
              maxLength={120}
              required
            />
          </div>
          {error ? <p className="text-xs text-destructive">{error}</p> : null}
          <Button type="submit" disabled={busy || name.trim().length < 2}>
            {busy ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <Plus className="mr-2 h-4 w-4" aria-hidden />
            )}
            创建租户
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function AcceptInvitationCard({
  onAccept,
}: {
  onAccept: (token: string) => Promise<void>;
}) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onAccept(token.trim());
      setToken("");
    } catch (submitError) {
      setError(errorMessage(submitError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserPlus className="h-4 w-4 text-muted-foreground" aria-hidden />
          接受成员邀请
        </CardTitle>
        <CardDescription>粘贴管理员提供的邀请令牌，加入已有企业。</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="invite-token">邀请令牌</Label>
            <Input
              id="invite-token"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="邀请令牌（仅展示一次）"
              minLength={16}
              required
            />
          </div>
          {error ? <p className="text-xs text-destructive">{error}</p> : null}
          <Button type="submit" variant="outline" disabled={busy || token.trim().length < 16}>
            {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            接受邀请
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function Overview({
  context,
  memberCount,
  aiCount,
  departmentCount,
  auditCount,
  invitationCount,
}: {
  context: TenantContext;
  memberCount: number;
  aiCount: number;
  departmentCount: number;
  auditCount: number;
  invitationCount: number;
}) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" aria-hidden />
            {context.name}
          </CardTitle>
          <CardDescription>
            租户标识 <span className="font-mono">{context.slug}</span> · 当前身份{" "}
            {context.member_display_name}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="成员总数" value={memberCount} hint={`其中 AI 员工 ${aiCount}`} />
          <Stat label="部门" value={departmentCount} hint="支持多级层级" />
          <Stat label="待处理邀请" value={invitationCount} hint="令牌方式邀请" />
          <Stat label="审计事件" value={auditCount} hint="最近 80 条" />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Phase 1 能力边界</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-xs text-muted-foreground">
          <p>已实现：账号认证、多租户切换、组织成员、部门层级、RBAC、邀请、审计、RLS 隔离。</p>
          <p>
            尚未实现：群聊与消息（Phase 2）、Agent Runtime（Phase 3）、任务与委派（Phase 4）。
            成员页中的 AI 员工目前只是组织身份，尚未拥有执行引擎。
          </p>
          <div className="pt-1">
            <Link className="text-primary hover:underline" href="/status">
              查看基础设施实时状态
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      <p className="text-[11px] text-muted-foreground">{hint}</p>
    </div>
  );
}

export default Workspace;

function MembersPanel({
  members,
  departments,
  roles,
  invitations,
  issuedInvite,
  canManage,
  canInvite,
  departmentName,
  onCreateAi,
  onUpdate,
  onSetRole,
  onInvite,
  onRevokeInvitation,
  onClearInvite,
}: {
  members: Member[];
  departments: Department[];
  roles: Role[];
  invitations: Invitation[];
  issuedInvite: InvitationCreated | null;
  canManage: boolean;
  canInvite: boolean;
  departmentName: (id: string | null) => string;
  onCreateAi: (input: {
    name: string;
    title: string;
    departmentId: string;
    roleKey: string;
  }) => Promise<void>;
  onUpdate: (id: string, payload: Record<string, unknown>) => Promise<void>;
  onSetRole: (id: string, roleKey: string) => Promise<void>;
  onInvite: (email: string, roleKey: string) => Promise<void>;
  onRevokeInvitation: (id: string) => Promise<void>;
  onClearInvite: () => void;
}) {
  const [aiName, setAiName] = useState("");
  const [aiTitle, setAiTitle] = useState("");
  const [aiDepartment, setAiDepartment] = useState("");
  const [aiRole, setAiRole] = useState("member");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function submitAi(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      await onCreateAi({
        name: aiName,
        title: aiTitle,
        departmentId: aiDepartment,
        roleKey: aiRole,
      });
      setAiName("");
      setAiTitle("");
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function submitInvite(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      await onInvite(inviteEmail, inviteRole);
      setInviteEmail("");
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function copyToken() {
    if (!issuedInvite) return;
    try {
      await navigator.clipboard.writeText(issuedInvite.token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  const pending = invitations.filter((invitation) => invitation.status === "pending");

  return (
    <div className="space-y-4">
      {canManage ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">创建 AI 员工</CardTitle>
            <CardDescription>
              创建后立即出现在组织成员列表；执行引擎将在 Phase 3 接入。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submitAi} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-1.5">
                <Label htmlFor="ai-name">姓名</Label>
                <Input
                  id="ai-name"
                  value={aiName}
                  onChange={(event) => setAiName(event.target.value)}
                  placeholder="例如：CTO-AI"
                  required
                  maxLength={120}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ai-title">岗位</Label>
                <Input
                  id="ai-title"
                  value={aiTitle}
                  onChange={(event) => setAiTitle(event.target.value)}
                  placeholder="例如：首席技术官"
                  maxLength={120}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ai-dept">部门</Label>
                <Select
                  id="ai-dept"
                  value={aiDepartment}
                  onChange={(event) => setAiDepartment(event.target.value)}
                >
                  <option value="">未分组</option>
                  {departments.map((department) => (
                    <option key={department.id} value={department.id}>
                      {department.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ai-role">角色</Label>
                <div className="flex gap-2">
                  <Select
                    id="ai-role"
                    value={aiRole}
                    onChange={(event) => setAiRole(event.target.value)}
                  >
                    {roles.map((role) => (
                      <option key={role.key} value={role.key}>
                        {ROLE_LABELS[role.key] ?? role.name}
                      </option>
                    ))}
                  </Select>
                  <Button type="submit" disabled={busy || aiName.trim().length < 1}>
                    <Plus className="h-4 w-4" aria-hidden />
                  </Button>
                </div>
              </div>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {canInvite ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">邀请人类成员</CardTitle>
            <CardDescription>
              系统生成一次性邀请令牌；当前阶段不会自动发送邮件，请由管理员安全传递。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <form onSubmit={submitInvite} className="grid gap-3 sm:grid-cols-[1fr_160px_auto]">
              <div className="space-y-1.5">
                <Label htmlFor="invite-email">邮箱</Label>
                <Input
                  id="invite-email"
                  type="email"
                  value={inviteEmail}
                  onChange={(event) => setInviteEmail(event.target.value)}
                  placeholder="new.member@company.com"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="invite-role">角色</Label>
                <Select
                  id="invite-role"
                  value={inviteRole}
                  onChange={(event) => setInviteRole(event.target.value)}
                >
                  {roles.map((role) => (
                    <option key={role.key} value={role.key}>
                      {ROLE_LABELS[role.key] ?? role.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex items-end">
                <Button type="submit" disabled={busy || !inviteEmail.trim()}>
                  <UserPlus className="mr-2 h-4 w-4" aria-hidden />
                  生成邀请
                </Button>
              </div>
            </form>

            {issuedInvite ? (
              <div className="rounded-md border bg-muted/30 p-3">
                <p className="text-xs font-medium">邀请令牌（仅展示一次）</p>
                <p className="mt-1 break-all font-mono text-[11px]">{issuedInvite.token}</p>
                <div className="mt-2 flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => void copyToken()}>
                    <ClipboardCopy className="mr-2 h-3.5 w-3.5" aria-hidden />
                    {copied ? "已复制" : "复制令牌"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={onClearInvite}>
                    关闭
                  </Button>
                </div>
              </div>
            ) : null}

            {pending.length > 0 ? (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">待接受邀请</p>
                {pending.map((invitation) => (
                  <div
                    key={invitation.id}
                    className="flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-xs"
                  >
                    <div>
                      <p className="font-medium">{invitation.email}</p>
                      <p className="text-muted-foreground">
                        {ROLE_LABELS[invitation.role_key] ?? invitation.role_key} · 过期{" "}
                        {formatTime(invitation.expires_at)}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => void onRevokeInvitation(invitation.id)}
                    >
                      撤销
                    </Button>
                  </div>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {formError ? <p className="text-xs text-destructive">{formError}</p> : null}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">组织成员 · {members.length}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-xs">
              <thead className="border-y bg-muted/30 text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 font-medium">成员</th>
                  <th className="px-4 py-2 font-medium">类型</th>
                  <th className="px-4 py-2 font-medium">部门 / 岗位</th>
                  <th className="px-4 py-2 font-medium">角色</th>
                  <th className="px-4 py-2 font-medium">状态</th>
                  <th className="px-4 py-2 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.id} className="border-b last:border-0">
                    <td className="px-4 py-2.5">
                      <p className="font-medium">{member.display_name}</p>
                      <p className="text-[11px] text-muted-foreground">
                        {member.user_id ? member.user_id.slice(0, 8) : "AI 身份"}
                      </p>
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge variant={member.member_type === "ai" ? "default" : "secondary"}>
                        {member.member_type === "ai" ? "AI" : "Human"}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      <p>{departmentName(member.department_id)}</p>
                      <p className="text-[11px] text-muted-foreground">{member.title ?? "—"}</p>
                    </td>
                    <td className="px-4 py-2.5">
                      {canManage ? (
                        <Select
                          value={member.roles[0]?.key ?? "member"}
                          onChange={(event) => void onSetRole(member.id, event.target.value)}
                          className="h-8 w-28 text-xs"
                        >
                          {roles.map((role) => (
                            <option key={role.key} value={role.key}>
                              {ROLE_LABELS[role.key] ?? role.name}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <span>{member.roles.map((role) => role.name).join(", ")}</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge variant={member.status === "active" ? "success" : "outline"}>
                        {member.status === "active" ? "启用" : "停用"}
                      </Badge>
                      {member.member_type === "ai" ? (
                        <p className="mt-1 text-[10px] text-muted-foreground">
                          AI {member.ai_enabled ? "开" : "关"}
                        </p>
                      ) : null}
                    </td>
                    <td className="px-4 py-2.5">
                      {canManage ? (
                        <div className="flex items-center gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() =>
                              void onUpdate(member.id, {
                                status: member.status === "active" ? "disabled" : "active",
                              })
                            }
                          >
                            {member.status === "active" ? "停用" : "启用"}
                          </Button>
                          {member.member_type === "ai" ? (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() =>
                                void onUpdate(member.id, { ai_enabled: !member.ai_enabled })
                              }
                            >
                              AI {member.ai_enabled ? "关闭" : "开启"}
                            </Button>
                          ) : null}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">只读</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function DepartmentsPanel({
  departments,
  canManage,
  onCreate,
  onDelete,
}: {
  departments: Department[];
  canManage: boolean;
  onCreate: (name: string, parentId: string | null) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      await onCreate(name, parentId || null);
      setName("");
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {canManage ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">新建部门</CardTitle>
            <CardDescription>部门支持多级层级，服务端阻止循环层级。</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[1fr_220px_auto]">
              <div className="space-y-1.5">
                <Label htmlFor="dept-name">部门名称</Label>
                <Input
                  id="dept-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="例如：研发部"
                  required
                  maxLength={120}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="dept-parent">上级部门</Label>
                <Select
                  id="dept-parent"
                  value={parentId}
                  onChange={(event) => setParentId(event.target.value)}
                >
                  <option value="">无（顶级部门）</option>
                  {departments.map((department) => (
                    <option key={department.id} value={department.id}>
                      {department.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex items-end">
                <Button type="submit" disabled={busy || !name.trim()}>
                  <Plus className="mr-2 h-4 w-4" aria-hidden />
                  创建
                </Button>
              </div>
            </form>
            {formError ? <p className="mt-2 text-xs text-destructive">{formError}</p> : null}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">部门结构 · {departments.length}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {departments.length === 0 ? (
            <p className="text-xs text-muted-foreground">尚未创建部门。</p>
          ) : null}
          {departments.map((department) => {
            const parent = departments.find((item) => item.id === department.parent_id);
            return (
              <div
                key={department.id}
                className="flex items-center justify-between gap-3 rounded-md border px-3 py-2.5"
              >
                <div className="flex items-start gap-2">
                  <Building2 className="mt-0.5 h-4 w-4 text-muted-foreground" aria-hidden />
                  <div>
                    <p className="text-sm font-medium">{department.name}</p>
                    <p className="text-[11px] text-muted-foreground">
                      上级：{parent?.name ?? "无"}
                    </p>
                  </div>
                </div>
                {canManage ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void onDelete(department.id)}
                    aria-label={`删除部门 ${department.name}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  </Button>
                ) : null}
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}

function AuditPanel({ logs, canRead }: { logs: AuditLog[]; canRead: boolean }) {
  if (!canRead) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
          <ShieldCheck className="h-4 w-4" aria-hidden />
          当前角色没有 audit.read 权限。
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">审计日志</CardTitle>
        <CardDescription>当前租户最近的事件，按时间倒序。</CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        {logs.length === 0 ? (
          <p className="px-4 py-6 text-xs text-muted-foreground">暂无审计事件。</p>
        ) : (
          <div className="divide-y">
            {logs.map((log) => (
              <div key={log.id} className="flex items-start justify-between gap-3 px-4 py-2.5">
                <div className="min-w-0">
                  <p className="font-mono text-xs">{log.action}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {log.actor_type} · {log.actor_id?.slice(0, 8) ?? "system"} ·{" "}
                    {log.resource_type}
                    {log.resource_id ? `:${log.resource_id.slice(0, 8)}` : ""}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <Badge variant={log.result === "success" ? "success" : "destructive"}>
                    {log.result}
                  </Badge>
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    {formatTime(log.created_at)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
