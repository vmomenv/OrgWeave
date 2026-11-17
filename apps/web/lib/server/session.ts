import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const API_BASE =
  process.env.API_INTERNAL_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

const ACCESS_COOKIE = "ow_access";
const REFRESH_COOKIE = "ow_refresh";
const ACCESS_MAX_AGE = 60 * 15;
const REFRESH_MAX_AGE = 60 * 60 * 24 * 30;
const COOKIE_SECURE = process.env.COOKIE_SECURE === "true";

let refreshInFlight: Promise<Record<string, unknown> | null> | null = null;

function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: COOKIE_SECURE,
    path: "/",
    maxAge,
  };
}

export function setSessionCookies(
  response: NextResponse,
  tokens: { access_token: string; refresh_token: string; expires_in?: number },
) {
  response.cookies.set(
    ACCESS_COOKIE,
    tokens.access_token,
    cookieOptions(tokens.expires_in ?? ACCESS_MAX_AGE),
  );
  response.cookies.set(
    REFRESH_COOKIE,
    tokens.refresh_token,
    cookieOptions(REFRESH_MAX_AGE),
  );
}

export function clearSessionCookies(response: NextResponse) {
  response.cookies.set(ACCESS_COOKIE, "", cookieOptions(0));
  response.cookies.set(REFRESH_COOKIE, "", cookieOptions(0));
}

async function refreshTokens(request: NextRequest): Promise<Record<string, unknown> | null> {
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
  if (!refreshToken) return null;
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
          cache: "no-store",
        });
        if (!response.ok) return null;
        return (await response.json()) as Record<string, unknown>;
      } catch {
        return null;
      }
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/**
 * Server-side call to the OrgWeave API using the httpOnly access cookie.
 * Refreshes once on 401. Returns the raw upstream response.
 */
export async function apiFetch(
  request: NextRequest,
  path: string,
  init: RequestInit = {},
): Promise<{ response: Response; newTokens: Record<string, unknown> | null }> {
  const accessToken = request.cookies.get(ACCESS_COOKIE)?.value;
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("authorization", `Bearer ${accessToken}`);

  const doFetch = () =>
    fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });

  let response = await doFetch();
  let newTokens: Record<string, unknown> | null = null;

  if (response.status === 401) {
    newTokens = await refreshTokens(request);
    const token = newTokens?.access_token;
    if (typeof token === "string") {
      headers.set("authorization", `Bearer ${token}`);
      response = await doFetch();
    }
  }

  return { response, newTokens };
}

export function withRefreshedCookies(
  response: NextResponse,
  newTokens: Record<string, unknown> | null,
) {
  if (!newTokens) return response;
  const access = newTokens.access_token;
  const refresh = newTokens.refresh_token;
  if (typeof access === "string" && typeof refresh === "string") {
    setSessionCookies(response, {
      access_token: access,
      refresh_token: refresh,
      expires_in: typeof newTokens.expires_in === "number" ? newTokens.expires_in : undefined,
    });
  }
  return response;
}

export function upstreamToNext(response: Response): NextResponse {
  return new NextResponse(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json",
    },
  });
}

export function isSameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  try {
    const originUrl = new URL(origin);
    return originUrl.host === request.headers.get("host");
  } catch {
    return false;
  }
}

export { ACCESS_COOKIE, API_BASE, REFRESH_COOKIE };
