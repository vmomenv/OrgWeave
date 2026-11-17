"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Loader2,
  MessageSquarePlus,
  Paperclip,
  Plus,
  Send,
  Users,
  Wifi,
  WifiOff,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  ApiClientError,
  uploadAttachment,
} from "@/lib/api-client";
import type { Attachment, Group, Member, Message } from "@/lib/api-client";
import { cn } from "@/lib/utils";

function errorMessage(error: unknown): string {
  if (error instanceof ApiClientError) return error.message;
  if (error instanceof Error) return error.message;
  return "操作失败";
}

function formatMessageTime(iso: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

function groupTitle(group: Group, currentMemberId: string): string {
  if (group.group_type === "channel") return group.name ?? "未命名群聊";
  const other = group.members.find((member) => member.member_id !== currentMemberId);
  return other ? `${other.display_name}（单聊）` : "单聊";
}

const WS_BASE = (process.env.NEXT_PUBLIC_WS_BASE_URL ?? "ws://localhost:8000/ws/v1").replace(
  /\/$/,
  "",
);

export function ChatPanel({
  tenantId,
  currentMemberId,
  members,
  canManage,
}: {
  tenantId: string;
  currentMemberId: string;
  members: Member[];
  canManage: boolean;
}) {
  const [groups, setGroups] = useState<Group[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [pendingAttachment, setPendingAttachment] = useState<Attachment | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  const selectedRef = useRef<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const selectedGroup = useMemo(
    () => groups.find((group) => group.id === selectedId) ?? null,
    [groups, selectedId],
  );

  const loadGroups = useCallback(async (): Promise<Group[]> => {
    const data = await api.get<Group[]>("groups", tenantId);
    setGroups(data);
    return data;
  }, [tenantId]);

  const loadMessages = useCallback(
    async (groupId: string) => {
      const data = await api.get<Message[]>(
        `groups/${groupId}/messages?limit=80`,
        tenantId,
      );
      setMessages(data);
      await api.post(`groups/${groupId}/read`, undefined, tenantId);
    },
    [tenantId],
  );

  useEffect(() => {
    selectedRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await loadGroups();
        if (!cancelled && data.length > 0) {
          setSelectedId((current) => current ?? data[0]?.id ?? null);
        }
      } catch (loadError) {
        if (!cancelled) setError(errorMessage(loadError));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadGroups]);

  useEffect(() => {
    if (!selectedId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    setBusy(true);
    (async () => {
      try {
        await loadMessages(selectedId);
        const refreshed = await loadGroups();
        if (!cancelled) {
          setGroups(refreshed);
        }
      } catch (loadError) {
        if (!cancelled) setError(errorMessage(loadError));
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, loadMessages, loadGroups]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  useEffect(() => {
    let disposed = false;
    let retried = false;
    let socket: WebSocket | null = null;

    async function connect() {
      try {
        const response = await fetch("/api/ws-token", { cache: "no-store" });
        if (!response.ok) return;
        const { token } = (await response.json()) as { token: string };
        if (disposed) return;
        socket = new WebSocket(
          `${WS_BASE}?token=${encodeURIComponent(token)}&tenant_id=${tenantId}`,
        );
        wsRef.current = socket;

        socket.onopen = () => setConnected(true);
        socket.onclose = async () => {
          setConnected(false);
          if (disposed || retried) return;
          retried = true;
          // Force a BFF refresh, then reconnect once with the new access cookie.
          await fetch("/api/auth/me", { cache: "no-store" }).catch(() => undefined);
          void connect();
        };
        socket.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data) as {
              type: string;
              group_id?: string;
              message?: Message;
            };
            if (payload.type === "message.created" && payload.group_id && payload.message) {
              if (selectedRef.current === payload.group_id) {
                setMessages((current) =>
                  current.some((item) => item.id === payload.message?.id)
                    ? current
                    : [...current, payload.message as Message],
                );
              }
              void loadGroups();
            }
          } catch {
            // Ignore malformed frames; the API controls the protocol.
          }
        };
      } catch {
        setConnected(false);
      }
    }

    void connect();
    return () => {
      disposed = true;
      socket?.close();
      wsRef.current = null;
    };
  }, [tenantId, loadGroups]);

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    if (!selectedId || (!draft.trim() && !pendingAttachment)) return;
    setBusy(true);
    setError(null);
    try {
      const message = await api.post<Message>(
        `groups/${selectedId}/messages`,
        {
          content: draft,
          attachment_ids: pendingAttachment ? [pendingAttachment.id] : [],
        },
        tenantId,
      );
      setDraft("");
      setPendingAttachment(null);
      setMessages((current) =>
        current.some((item) => item.id === message.id) ? current : [...current, message],
      );
      await loadGroups();
    } catch (sendError) {
      setError(errorMessage(sendError));
    } finally {
      setBusy(false);
    }
  }

  async function uploadFile(file: File) {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      const attachment = await uploadAttachment(selectedId, file, tenantId);
      setPendingAttachment(attachment);
    } catch (uploadError) {
      setError(errorMessage(uploadError));
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleCreated(group: Group) {
    setShowCreate(false);
    const refreshed = await loadGroups();
    setGroups(refreshed);
    setSelectedId(group.id);
    wsRef.current?.send(JSON.stringify({ type: "resubscribe" }));
  }

  async function addMembers(memberIds: string[]) {
    if (!selectedId) return;
    setBusy(true);
    try {
      await api.post(`groups/${selectedId}/members`, { member_ids: memberIds }, tenantId);
      const refreshed = await loadGroups();
      setGroups(refreshed);
      wsRef.current?.send(JSON.stringify({ type: "resubscribe" }));
    } catch (addError) {
      setError(errorMessage(addError));
    } finally {
      setBusy(false);
    }
  }

  function insertMention(name: string) {
    setDraft((current) => `${current}${current && !current.endsWith(" ") ? " " : ""}@${name} `);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <MessageSquarePlus className="h-4 w-4" aria-hidden />
          群聊与单聊 · 消息实时同步
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "flex items-center gap-1 text-[11px]",
              connected ? "text-success" : "text-muted-foreground",
            )}
          >
            {connected ? (
              <Wifi className="h-3.5 w-3.5" aria-hidden />
            ) : (
              <WifiOff className="h-3.5 w-3.5" aria-hidden />
            )}
            {connected ? "实时已连接" : "实时未连接"}
          </span>
          <Button size="sm" variant="outline" onClick={() => setShowCreate((value) => !value)}>
            <Plus className="mr-1.5 h-3.5 w-3.5" aria-hidden />
            新建会话
          </Button>
        </div>
      </div>

      {error ? <p className="text-xs text-destructive">{error}</p> : null}

      {showCreate ? (
        <CreateGroupForm
          tenantId={tenantId}
          members={members}
          currentMemberId={currentMemberId}
          onCreate={handleCreated}
          onError={(message) => setError(message)}
        />
      ) : null}

      <div className="grid min-h-[560px] gap-3 lg:grid-cols-[230px_1fr]">
        <Card className="overflow-hidden">
          <CardHeader className="border-b px-3 py-2.5">
            <CardTitle className="flex items-center gap-2 text-xs">
              <Users className="h-3.5 w-3.5" aria-hidden />
              会话 · {groups.length}
            </CardTitle>
          </CardHeader>
          <CardContent className="max-h-[520px] space-y-0.5 overflow-y-auto p-1.5">
            {groups.length === 0 ? (
              <p className="px-2 py-6 text-xs text-muted-foreground">
                还没有会话，点击“新建会话”开始。
              </p>
            ) : null}
            {groups.map((group) => (
              <button
                key={group.id}
                type="button"
                onClick={() => setSelectedId(group.id)}
                className={cn(
                  "flex w-full flex-col gap-0.5 rounded-md px-2 py-2 text-left transition-colors",
                  selectedId === group.id ? "bg-accent" : "hover:bg-accent/60",
                )}
              >
                <span className="flex w-full items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">
                    {groupTitle(group, currentMemberId)}
                  </span>
                  {group.unread_count > 0 ? (
                    <span className="shrink-0 rounded-full bg-primary px-1.5 text-[10px] text-primary-foreground">
                      {group.unread_count}
                    </span>
                  ) : null}
                </span>
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate text-[11px] text-muted-foreground">
                    {group.last_message?.content ?? "暂无消息"}
                  </span>
                  <Badge variant="outline" className="shrink-0 px-1 py-0 text-[9px]">
                    {group.group_type === "direct" ? "单聊" : "群聊"}
                  </Badge>
                </span>
              </button>
            ))}
          </CardContent>
        </Card>

        <Card className="flex min-h-[560px] flex-col overflow-hidden">
          {selectedGroup ? (
            <>
              <CardHeader className="flex-row items-center justify-between space-y-0 border-b px-4 py-2.5">
                <div>
                  <CardTitle className="text-sm">
                    {groupTitle(selectedGroup, currentMemberId)}
                  </CardTitle>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    {selectedGroup.members.length} 名成员 ·{" "}
                    {selectedGroup.members.filter((member) => member.member_type === "ai").length}{" "}
                    名 AI
                  </p>
                </div>
                {canManage && selectedGroup.group_type === "channel" ? (
                  <AddMemberControl
                    members={members.filter(
                      (member) =>
                        !selectedGroup.members.some(
                          (existing) => existing.member_id === member.id,
                        ),
                    )}
                    onAdd={addMembers}
                  />
                ) : null}
              </CardHeader>

              <CardContent className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
                {busy && messages.length === 0 ? (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                    加载消息…
                  </div>
                ) : null}
                {messages.length === 0 && !busy ? (
                  <p className="py-10 text-center text-xs text-muted-foreground">
                    暂无消息，发送第一条消息开始协作。
                  </p>
                ) : null}
                {messages.map((message) => (
                  <div key={message.id} className="flex gap-2.5">
                    <span
                      className={cn(
                        "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold",
                        message.sender.member_type === "ai"
                          ? "bg-primary/15 text-primary"
                          : "bg-muted text-muted-foreground",
                      )}
                    >
                      {message.sender.display_name.slice(0, 2)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-xs font-medium">
                          {message.sender.display_name}
                        </span>
                        {message.sender.member_type === "ai" ? (
                          <Badge className="px-1 py-0 text-[9px]">AI</Badge>
                        ) : null}
                        <span className="text-[10px] text-muted-foreground">
                          {formatMessageTime(message.created_at)}
                        </span>
                        {message.parent_message_id ? (
                          <span className="text-[10px] text-muted-foreground">↳ 回复</span>
                        ) : null}
                      </div>
                      <p className="whitespace-pre-wrap break-words text-sm">
                        {message.content || "（附件）"}
                      </p>
                      {message.mentions.length > 0 ? (
                        <p className="mt-0.5 text-[10px] text-muted-foreground">
                          提及：{message.mentions.map((mention) => mention.display_name).join("、")}
                        </p>
                      ) : null}
                      {message.attachments.length > 0 ? (
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {message.attachments.map((attachment) => (
                            <a
                              key={attachment.id}
                              href={`/api/proxy/attachments/${attachment.id}?tenant_id=${tenantId}`}
                              className="inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] text-primary hover:bg-accent"
                            >
                              <Paperclip className="h-3 w-3" aria-hidden />
                              {attachment.filename}
                              <span className="text-muted-foreground">
                                {Math.ceil(attachment.size_bytes / 1024)} KB
                              </span>
                            </a>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </CardContent>

              <div className="border-t p-3">
                <div className="mb-2 flex flex-wrap gap-1">
                  {selectedGroup.members
                    .filter((member) => member.member_id !== currentMemberId)
                    .map((member) => (
                      <button
                        key={member.member_id}
                        type="button"
                        onClick={() => insertMention(member.display_name)}
                        className="rounded-full border px-2 py-0.5 text-[10px] text-muted-foreground hover:bg-accent hover:text-foreground"
                      >
                        @{member.display_name}
                        {member.member_type === "ai" ? " · AI" : ""}
                      </button>
                    ))}
                </div>
                {pendingAttachment ? (
                  <div className="mb-2 flex items-center justify-between rounded-md border bg-muted/30 px-2 py-1 text-[11px]">
                    <span className="truncate">
                      <Paperclip className="mr-1 inline h-3 w-3" aria-hidden />
                      {pendingAttachment.filename}
                    </span>
                    <button
                      type="button"
                      className="text-muted-foreground hover:text-foreground"
                      onClick={() => setPendingAttachment(null)}
                    >
                      移除
                    </button>
                  </div>
                ) : null}
                <form onSubmit={sendMessage} className="flex items-end gap-2">
                  <Textarea
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder="输入消息，使用 @ 提及成员或 AI 员工…"
                    className="min-h-[44px] flex-1 resize-none"
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        event.currentTarget.form?.requestSubmit();
                      }
                    }}
                  />
                  <input
                    ref={fileInputRef}
                    type="file"
                    className="hidden"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) void uploadFile(file);
                    }}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={() => fileInputRef.current?.click()}
                    aria-label="添加附件"
                  >
                    <Paperclip className="h-4 w-4" aria-hidden />
                  </Button>
                  <Button
                    type="submit"
                    size="icon"
                    disabled={busy || (!draft.trim() && !pendingAttachment)}
                    aria-label="发送消息"
                  >
                    <Send className="h-4 w-4" aria-hidden />
                  </Button>
                </form>
              </div>
            </>
          ) : (
            <CardContent className="flex flex-1 items-center justify-center p-6 text-sm text-muted-foreground">
              选择一个会话查看消息
            </CardContent>
          )}
        </Card>
      </div>
    </div>
  );
}

function CreateGroupForm({
  tenantId,
  members,
  currentMemberId,
  onCreate,
  onError,
}: {
  tenantId: string;
  members: Member[];
  currentMemberId: string;
  onCreate: (group: Group) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState<"channel" | "direct">("channel");
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const candidates = members.filter(
    (member) => member.id !== currentMemberId && member.status === "active",
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const group = await api.post<Group>(
        "groups",
        {
          name: type === "channel" ? name : null,
          group_type: type,
          member_ids: selected,
        },
        tenantId,
      );
      await onCreate(group);
      setName("");
      setSelected([]);
    } catch (error) {
      onError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">新建会话</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-[160px_1fr]">
            <div className="space-y-1.5">
              <Label htmlFor="group-type">类型</Label>
              <Select
                id="group-type"
                value={type}
                onChange={(event) => {
                  setType(event.target.value as "channel" | "direct");
                  setSelected([]);
                }}
              >
                <option value="channel">群聊</option>
                <option value="direct">单聊</option>
              </Select>
            </div>
            {type === "channel" ? (
              <div className="space-y-1.5">
                <Label htmlFor="group-name">群名称</Label>
                <Input
                  id="group-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="例如：产品研发协作群"
                  required
                  maxLength={120}
                />
              </div>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label>选择成员</Label>
            <div className="flex max-h-36 flex-wrap gap-1.5 overflow-y-auto rounded-md border p-2">
              {candidates.length === 0 ? (
                <p className="text-[11px] text-muted-foreground">
                  当前没有其他成员，请先在“成员”页创建 AI 员工或邀请人类成员。
                </p>
              ) : null}
              {candidates.map((member) => {
                const checked = selected.includes(member.id);
                return (
                  <button
                    key={member.id}
                    type="button"
                    onClick={() => {
                      if (type === "direct") {
                        setSelected([member.id]);
                        return;
                      }
                      setSelected((current) =>
                        checked
                          ? current.filter((id) => id !== member.id)
                          : [...current, member.id],
                      );
                    }}
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                      checked
                        ? "border-primary bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-accent",
                    )}
                  >
                    {member.display_name}
                    {member.member_type === "ai" ? " · AI" : ""}
                  </button>
                );
              })}
            </div>
          </div>

          <Button
            type="submit"
            size="sm"
            disabled={
              busy ||
              selected.length === 0 ||
              (type === "channel" && name.trim().length === 0) ||
              (type === "direct" && selected.length !== 1)
            }
          >
            {busy ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" aria-hidden /> : null}
            创建会话
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function AddMemberControl({
  members,
  onAdd,
}: {
  members: Member[];
  onAdd: (ids: string[]) => Promise<void>;
}) {
  const [memberId, setMemberId] = useState("");
  return (
    <div className="flex items-center gap-1">
      <Select
        value={memberId}
        onChange={(event) => setMemberId(event.target.value)}
        className="h-8 w-36 text-xs"
        aria-label="选择要加入群聊的成员"
      >
        <option value="">邀请成员…</option>
        {members.map((member) => (
          <option key={member.id} value={member.id}>
            {member.display_name}
          </option>
        ))}
      </Select>
      <Button
        size="icon"
        variant="outline"
        className="h-8 w-8"
        disabled={!memberId}
        onClick={() => {
          if (!memberId) return;
          void onAdd([memberId]);
          setMemberId("");
        }}
        aria-label="加入群聊"
      >
        <Plus className="h-3.5 w-3.5" aria-hidden />
      </Button>
    </div>
  );
}
