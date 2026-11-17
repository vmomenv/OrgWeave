import type {
  HealthSnapshot,
  MetaResponse,
  ReadinessResponse,
} from "@orgweave/shared-types";

export const API_INTERNAL_URL =
  process.env.API_INTERNAL_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

const TIMEOUT_MS = 4000;

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_INTERNAL_URL}${path}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(TIMEOUT_MS),
    ...init,
  });
  if (!response.ok && response.status !== 503) {
    throw new Error(`${path} returned HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function getHealthSnapshot(): Promise<HealthSnapshot> {
  const checkedAt = new Date().toISOString();
  try {
    const [readiness, meta] = await Promise.all([
      fetchJson<ReadinessResponse>("/api/v1/health/ready"),
      fetchJson<MetaResponse>("/api/v1/meta"),
    ]);
    return { readiness, meta, error: null, checkedAt };
  } catch (error) {
    return {
      readiness: null,
      meta: null,
      error:
        error instanceof Error
          ? error.message
          : "无法连接 OrgWeave API，请确认后端已启动。",
      checkedAt,
    };
  }
}
