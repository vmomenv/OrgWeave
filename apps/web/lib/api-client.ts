export class ApiClientError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  tenantId?: string | null;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["content-type"] = "application/json";
  if (options.tenantId) headers["X-Tenant-ID"] = options.tenantId;

  const response = await fetch(`/api/proxy/${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store",
  });

  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = payload?.error;
    throw new ApiClientError(
      response.status,
      error?.code ?? "request_failed",
      error?.message ?? `请求失败（HTTP ${response.status}）`,
      error?.details,
    );
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string, tenantId?: string | null) => request<T>(path, { tenantId }),
  post: <T>(path: string, body?: unknown, tenantId?: string | null) =>
    request<T>(path, { method: "POST", body, tenantId }),
  put: <T>(path: string, body?: unknown, tenantId?: string | null) =>
    request<T>(path, { method: "PUT", body, tenantId }),
  patch: <T>(path: string, body?: unknown, tenantId?: string | null) =>
    request<T>(path, { method: "PATCH", body, tenantId }),
  del: <T>(path: string, tenantId?: string | null) =>
    request<T>(path, { method: "DELETE", tenantId }),
};

export type User = {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  created_at: string;
};

export type TenantSummary = {
  id: string;
  name: string;
  slug: string;
  membership_status: string;
  role_keys: string[];
};

export type MeResponse = { user: User; tenants: TenantSummary[] };

export type TenantContext = {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  membership_status: string;
  member_id: string;
  member_display_name: string;
  role_keys: string[];
  permissions: string[];
};

export type Department = {
  id: string;
  name: string;
  parent_id: string | null;
  created_at: string;
  updated_at: string;
};

export type RoleSummary = { key: string; name: string };

export type Member = {
  id: string;
  member_type: "human" | "ai";
  user_id: string | null;
  display_name: string;
  title: string | null;
  bio: string | null;
  avatar_url: string | null;
  department_id: string | null;
  manager_id: string | null;
  status: "active" | "disabled";
  ai_enabled: boolean;
  created_at: string;
  updated_at: string;
  roles: RoleSummary[];
};

export type Role = RoleSummary & {
  description: string;
  is_system: boolean;
  permissions: string[];
};

export type Invitation = {
  id: string;
  email: string;
  role_key: string;
  status: string;
  expires_at: string;
  created_at: string;
};

export type InvitationCreated = Invitation & { token: string };

export type AuditLog = {
  id: string;
  tenant_id: string | null;
  actor_type: string;
  actor_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  result: string;
  metadata: Record<string, unknown>;
  created_at: string;
};


export type GroupMemberInfo = {
  member_id: string;
  display_name: string;
  member_type: string;
  title: string | null;
  role: string;
  joined_at: string;
  last_read_at: string | null;
};

export type Attachment = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

export type MemberRef = {
  id: string;
  display_name: string;
  member_type: string;
};

export type Message = {
  id: string;
  group_id: string;
  sender: MemberRef;
  content: string;
  content_type: string;
  parent_message_id: string | null;
  mentions: MemberRef[];
  attachments: Attachment[];
  metadata: Record<string, unknown>;
  created_at: string;
  edited_at: string | null;
};

export type Group = {
  id: string;
  name: string | null;
  group_type: "channel" | "direct";
  created_at: string;
  updated_at: string;
  members: GroupMemberInfo[];
  last_message: Message | null;
  unread_count: number;
};

export async function uploadAttachment(
  groupId: string,
  file: File,
  tenantId: string,
): Promise<Attachment> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`/api/proxy/groups/${groupId}/attachments`, {
    method: "POST",
    headers: { "X-Tenant-ID": tenantId },
    body: form,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiClientError(
      response.status,
      payload?.error?.code ?? "upload_failed",
      payload?.error?.message ?? "附件上传失败",
    );
  }
  return payload as Attachment;
}
