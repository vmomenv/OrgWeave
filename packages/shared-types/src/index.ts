/**
 * Wire contracts shared by the web client and the OrgWeave API.
 * Keep these aligned with apps/api/app/schemas/health.py.
 */

export type DependencyStatus = "ok" | "error";
export type ReadinessStatus = "ready" | "degraded";

export interface DependencyCheck {
  name: string;
  status: DependencyStatus;
  latency_ms: number;
  detail: string | null;
}

export interface ReadinessResponse {
  status: ReadinessStatus;
  version: string;
  timestamp: string;
  checks: DependencyCheck[];
}

export interface LivenessResponse {
  status: "ok";
  service: string;
  version: string;
  timestamp: string;
}

export interface MetaResponse {
  name: string;
  api_version: string;
  phase: string;
  version: string;
  api_prefix: string;
  ws_prefix: string;
  openapi_url: string;
  docs_url: string;
}

export interface HealthSnapshot {
  readiness: ReadinessResponse | null;
  meta: MetaResponse | null;
  error: string | null;
  checkedAt: string;
}
